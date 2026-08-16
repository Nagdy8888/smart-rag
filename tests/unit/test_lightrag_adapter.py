"""Unit tests for LightRAG runtime attach guards and settings isolation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import SecretStr
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_SEARCH_PATH,
    RUNTIME_COSINE_BETTER_THAN_THRESHOLD,
    RUNTIME_POSTGRES_MAX_CONNECTIONS,
)
from smart_rag_core.retrieval.lightrag_adapter import (
    LightRagAdapterError,
    adapter_mode_label,
    apply_lightrag_postgres_env,
    assert_embedding_pin,
    assert_postgres_workspace_unset,
    assert_search_path,
    bootstrap_server_settings,
    cosine_threshold_for_mode,
    load_reviewed_fingerprint_fixture,
    reviewed_schema_manifest,
    runtime_server_settings,
    search_path_from_server_settings,
)
from smart_rag_core.retrieval.lightrag_qualification import (
    QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD,
    is_fatal_initialize_warning,
    parse_postgres_url,
)
from smart_rag_core.settings import (
    BackendSettings,
    LightRagSchemaAdminSettings,
    SharedSettings,
    WorkerSettings,
)
from smart_rag_core.settings.agents import AgentSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "lightrag" / "schema_fingerprint_v1.json"
OPS_SCRIPT = REPO_ROOT / "scripts" / "ops" / "bootstrap_lightrag_schema.py"


def _settings_from_env(factory: object) -> LightRagSchemaAdminSettings:
    """Construct schema-admin settings from process environment.

    Args:
        factory: ``LightRagSchemaAdminSettings`` class object.

    Returns:
        Validated settings loaded from env.

    Raises:
        TypeError: If ``factory`` is not a callable settings class.
    """

    if not callable(factory):
        raise TypeError("LightRagSchemaAdminSettings must be callable")
    loaded = factory()
    if not isinstance(loaded, LightRagSchemaAdminSettings):
        raise TypeError("expected LightRagSchemaAdminSettings")
    return loaded


def test_reviewed_fixture_matches_pin_manifest() -> None:
    """The committed fingerprint fixture must list the reviewed vendor tables."""

    fixture = load_reviewed_fingerprint_fixture(FIXTURE)
    manifest = reviewed_schema_manifest()
    assert fixture.tables == manifest.tables
    assert fixture.search_path == LIGHTRAG_SEARCH_PATH
    assert fixture.embedding_dimensions == 1024


def test_postgres_workspace_env_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime must not honor ``POSTGRES_WORKSPACE``."""

    monkeypatch.setenv("POSTGRES_WORKSPACE", "forced")
    with pytest.raises(LightRagAdapterError, match="postgres_workspace_env_override"):
        assert_postgres_workspace_unset()


def test_wrong_search_path_fails_closed() -> None:
    """Uncontrolled search_path must fail closed."""

    with pytest.raises(LightRagAdapterError, match="wrong_search_path"):
        assert_search_path("public")
    assert_search_path(LIGHTRAG_SEARCH_PATH)


def test_incompatible_vector_config_fails_closed() -> None:
    """A second model/dimension is not allowed in this process."""

    with pytest.raises(LightRagAdapterError, match="incompatible_vector_config"):
        assert_embedding_pin(model_name="text-embedding-3-large", dimensions=1536)
    with pytest.raises(LightRagAdapterError, match="incompatible_vector_config"):
        assert_embedding_pin(model_name="text-embedding-3-small", dimensions=1024)
    assert_embedding_pin(model_name="text-embedding-3-large", dimensions=1024)


def test_runtime_server_settings_use_controlled_search_path() -> None:
    """Runtime and bootstrap share search_path; role is applied via SET ROLE."""

    runtime = runtime_server_settings()
    bootstrap = bootstrap_server_settings()
    assert search_path_from_server_settings(runtime) == LIGHTRAG_SEARCH_PATH
    assert search_path_from_server_settings(bootstrap) == LIGHTRAG_SEARCH_PATH
    assert "session_authorization" not in runtime
    assert "session_authorization" not in bootstrap


def test_pool_cap_rejects_values_above_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process LightRAG pools cannot exceed cap 4."""

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    params = parse_postgres_url(
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )
    with pytest.raises(
        LightRagAdapterError, match="postgres_max_connections_out_of_range"
    ):
        apply_lightrag_postgres_env(
            params,
            max_connections=RUNTIME_POSTGRES_MAX_CONNECTIONS + 1,
            server_settings=runtime_server_settings(),
        )


def test_schema_admin_secret_is_absent_from_runtime_settings() -> None:
    """Schema-admin DSN must not exist on Shared/Backend/Worker/Agent settings."""

    for settings_cls in (
        SharedSettings,
        BackendSettings,
        WorkerSettings,
        AgentSettings,
    ):
        assert "lightrag_schema_admin_dsn" not in settings_cls.model_fields
        aliases = {
            field.validation_alias
            for field in settings_cls.model_fields.values()
            if isinstance(field.validation_alias, str)
        }
        assert "LIGHTRAG_SCHEMA_ADMIN_DSN" not in aliases
    assert "lightrag_db_url" in BackendSettings.model_fields
    assert "lightrag_db_url" in WorkerSettings.model_fields
    assert "lightrag_db_url" not in SharedSettings.model_fields
    assert "lightrag_db_url" not in AgentSettings.model_fields
    assert adapter_mode_label(None) == "unconfigured"


def test_schema_admin_settings_load_in_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema-admin DSN loads only through operations settings."""

    monkeypatch.setenv(
        "LIGHTRAG_SCHEMA_ADMIN_DSN",
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    )
    loaded = _settings_from_env(LightRagSchemaAdminSettings)
    assert isinstance(loaded.lightrag_schema_admin_dsn, SecretStr)
    assert "postgres:postgres" not in repr(loaded)


def test_fatal_initialize_warning_fails_closed() -> None:
    """Incomplete-migration warnings are not treated as success."""

    assert is_fatal_initialize_warning("incomplete migration detected") is True
    assert is_fatal_initialize_warning("Could not create VECTOR extension") is True
    assert is_fatal_initialize_warning("workspace data in table is empty") is False


def test_ops_bootstrap_script_does_not_import_lightrag() -> None:
    """The ops CLI must call core bootstrap instead of importing vendor classes."""

    tree = ast.parse(OPS_SCRIPT.read_text(encoding="utf-8"), filename=str(OPS_SCRIPT))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "lightrag"
                assert not alias.name.startswith("lightrag.")
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module != "lightrag"
            assert not node.module.startswith("lightrag.")


def test_cosine_threshold_uses_mock_floor_only_in_mock_mode() -> None:
    """Mock attach uses -1.0; live Graph keeps the 0.2 production pin."""

    assert (
        cosine_threshold_for_mode(mock_model_mode=True)
        == QUALIFICATION_COSINE_BETTER_THAN_THRESHOLD
    )
    assert (
        cosine_threshold_for_mode(mock_model_mode=False)
        == RUNTIME_COSINE_BETTER_THAN_THRESHOLD
    )
