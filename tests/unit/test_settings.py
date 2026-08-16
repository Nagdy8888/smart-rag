"""Unit tests for centralized deployable settings validation."""

from __future__ import annotations

import pytest
from smart_rag_core.settings import (
    AgentSettings,
    BackendSettings,
    Environment,
    JwksRolloverSettings,
    SettingsValidationError,
    WorkerSettings,
    load_backend_settings,
    load_jwks_rollover_settings,
    load_worker_settings,
)


def test_deployable_settings_are_typed_and_share_secure_defaults() -> None:
    """All deployable settings inherit deterministic mock-mode defaults."""

    backend = BackendSettings()
    worker = WorkerSettings()
    agents = AgentSettings()

    assert backend.app_env is Environment.LOCAL
    assert backend.mock_model_mode is True
    assert backend.service_name == "backend"
    assert worker.service_name == "worker"
    assert agents.service_name == "agents"


def test_backend_settings_load_documented_environment_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend aliases parse typed values only through the settings boundary."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    monkeypatch.setenv("API_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("API_BIND_PORT", "8123")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-this-value-must-remain-secret")

    settings = load_backend_settings()

    assert settings.app_env is Environment.TEST
    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 8123
    assert settings.openai_api_key is not None
    assert (
        settings.openai_api_key.get_secret_value() == "sk-this-value-must-remain-secret"
    )
    assert "sk-this-value" not in repr(settings)


def test_wildcard_cors_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentialed wildcard CORS cannot be configured."""

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example,*")
    with pytest.raises(SettingsValidationError):
        load_backend_settings()


def test_backend_cache_ttl_and_api_version_defaults() -> None:
    """Packet 5 cache TTLs and handshake versions have signed defaults."""

    settings = BackendSettings()
    assert settings.retrieval_cache_result_ttl_seconds == 30
    assert settings.retrieval_cache_profile_ttl_seconds == 300
    assert settings.api_version == "0.1.0"
    assert settings.sse_schema_version == "1"
    assert settings.parsed_cors_origins() == (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )


def test_settings_validation_error_omits_invalid_source_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanitized startup errors list field/type but never the input value."""

    invalid_source_value = "not-a-port-value-12345"
    monkeypatch.setenv("API_BIND_PORT", invalid_source_value)

    with pytest.raises(SettingsValidationError) as caught:
        load_backend_settings()

    message = str(caught.value)
    assert "API_BIND_PORT" in message
    assert invalid_source_value not in message


def test_real_model_mode_requires_provider_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabling fixtures without a provider key fails startup validation."""

    monkeypatch.setenv("MOCK_MODEL_MODE", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SettingsValidationError):
        load_backend_settings()


def test_worker_one_shot_flag_loads_through_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker smoke-test switch is parsed only by its typed loader."""

    monkeypatch.setenv("WORKER_ONCE", "true")
    assert load_worker_settings().worker_once is True


def test_worker_checkpoint_url_falls_back_to_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkpointer DSN reuses ``SUPABASE_DB_URL`` when the dedicated var is unset."""

    monkeypatch.setenv(
        "SUPABASE_DB_URL",
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    )
    monkeypatch.delenv("LANGGRAPH_CHECKPOINT_URL", raising=False)
    settings = load_worker_settings()
    assert settings.langgraph_checkpoint_url is None
    assert settings.resolved_checkpoint_dsn() == (
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )

    monkeypatch.setenv(
        "LANGGRAPH_CHECKPOINT_URL",
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    )
    dedicated = load_worker_settings()
    assert dedicated.langgraph_checkpoint_url is not None
    assert (
        dedicated.resolved_checkpoint_dsn()
        == "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )


def test_jwks_operation_settings_validate_and_redact_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Managed rollover settings validate endpoints without exposing tokens."""

    access_token = "local-management-proof-token"  # noqa: S105 - inert fixture
    anon_key = "local-publishable-proof-key"
    monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", access_token)
    monkeypatch.setenv("SUPABASE_PROJECT_REF", "abcdefghijklmnopqrst")
    monkeypatch.setenv("SUPABASE_MANAGED_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", anon_key)

    settings = load_jwks_rollover_settings()

    assert isinstance(settings, JwksRolloverSettings)
    assert settings.supabase_project_ref == "abcdefghijklmnopqrst"
    assert access_token not in repr(settings)
    assert anon_key not in repr(settings)
