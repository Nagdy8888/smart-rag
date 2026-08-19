"""Prove privileged/bootstrap secrets are absent from general runtime settings.

This scan inspects **declared settings field names and env aliases only**.
Isolated privileged module paths (``smart_rag_api.storage_admin``), loader
names (``load_privileged_storage_settings``), and class names must not fail
the check. A ``storage_admin`` substring on a Shared/Backend/Worker/Agent
**field or env alias** remains a failure.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from smart_rag_api.auth_admin.settings import load_privileged_auth_settings
from smart_rag_api.storage_admin.settings import (
    PrivilegedStorageSettings,
    load_privileged_storage_settings,
)
from smart_rag_core.settings import BackendSettings, SharedSettings, WorkerSettings
from smart_rag_core.settings.agents import AgentSettings
from smart_rag_worker.privileged_storage import load_worker_privileged_storage_secret

RUNTIME_SETTINGS_CLASSES: tuple[type[BaseSettings], ...] = (
    SharedSettings,
    BackendSettings,
    WorkerSettings,
    AgentSettings,
)

FORBIDDEN_FIELD_FRAGMENTS = (
    "auth_admin",
    "storage_admin",
    "service_role",
    "bootstrap",
    "migration_secret",
    "migration_password",
    "supabase_service",
)

FORBIDDEN_ENV_FRAGMENTS = (
    "AUTH_ADMIN",
    "STORAGE_ADMIN",
    "SERVICE_ROLE",
    "BOOTSTRAP",
    "MIGRATION_SECRET",
)


def _field_names(settings_cls: type[BaseModel]) -> set[str]:
    """Return lowercased model field names for one settings class.

    Args:
        settings_cls: Pydantic model whose declared fields are scanned.

    Returns:
        Lowercased field names. Class ``__name__`` and ``__module__`` are
        intentionally omitted so isolated package names cannot false-fail.
    """

    return {name.lower() for name in settings_cls.model_fields}


def _alias_strings(alias: object) -> set[str]:
    """Flatten one Pydantic alias value into uppercase strings.

    Args:
        alias: String validation/serialization alias, or ``None``.

    Returns:
        Uppercased alias tokens. Empty when ``alias`` is not a string.
        Isolated module/class names are never collected here.
    """

    if isinstance(alias, str):
        return {alias.upper()}
    return set()


def _alias_names(settings_cls: type[BaseModel]) -> set[str]:
    """Return uppercased validation aliases for one settings class.

    Args:
        settings_cls: Pydantic model whose env aliases are scanned.

    Returns:
        Uppercased alias tokens from field aliases only.
    """

    aliases: set[str] = set()
    for field in settings_cls.model_fields.values():
        aliases.update(_alias_strings(field.validation_alias))
        aliases.update(_alias_strings(field.serialization_alias))
        if field.alias:
            aliases.add(str(field.alias).upper())
    return aliases


def assert_settings_omit_privileged_secret_names(
    settings_cls: type[BaseModel],
) -> None:
    """Fail when a settings class declares a privileged secret field or env name.

    Args:
        settings_cls: Runtime settings class under test.

    Raises:
        AssertionError: If a field name or env alias contains a forbidden
            privileged-secret fragment.
    """

    names = _field_names(settings_cls)
    aliases = _alias_names(settings_cls)
    for fragment in FORBIDDEN_FIELD_FRAGMENTS:
        assert not any(fragment in name for name in names), (
            f"{settings_cls.__name__} field matches forbidden fragment {fragment}"
        )
    for fragment in FORBIDDEN_ENV_FRAGMENTS:
        assert not any(fragment in alias for alias in aliases), (
            f"{settings_cls.__name__} alias matches forbidden fragment {fragment}"
        )


def test_privileged_secrets_absent_from_runtime_settings() -> None:
    """Shared/Backend/Worker/Agent settings must not declare privileged secrets."""

    for settings_cls in RUNTIME_SETTINGS_CLASSES:
        assert_settings_omit_privileged_secret_names(settings_cls)


def test_isolated_privileged_module_names_do_not_fail_the_scan() -> None:
    """Package and loader names containing ``storage_admin`` are not secrets.

    Importing ``smart_rag_api.storage_admin.settings`` and
    ``load_privileged_storage_settings`` must not fail the runtime scan.
    """

    assert "storage_admin" in PrivilegedStorageSettings.__module__
    assert "storage_admin" in load_privileged_storage_settings.__module__
    assert load_privileged_storage_settings.__name__ == (
        "load_privileged_storage_settings"
    )

    class IsolatedPrivilegedLoader(BaseModel):
        """Stand-in whose name matches an isolated privileged package."""

        timeout_seconds: int = 1

    IsolatedPrivilegedLoader.__name__ = "storage_admin_settings"
    IsolatedPrivilegedLoader.__qualname__ = "storage_admin_settings"
    IsolatedPrivilegedLoader.__module__ = "smart_rag_api.storage_admin.settings"
    assert "storage_admin" in IsolatedPrivilegedLoader.__name__
    assert "storage_admin" in IsolatedPrivilegedLoader.__module__
    assert_settings_omit_privileged_secret_names(IsolatedPrivilegedLoader)
    for settings_cls in RUNTIME_SETTINGS_CLASSES:
        assert_settings_omit_privileged_secret_names(settings_cls)


def test_worker_refuses_inprocess_parser_when_storage_admin_secret_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-process parser plus Storage Admin in the same process must not start."""

    from smart_rag_core.jobs.exceptions import JobRepositoryError
    from smart_rag_worker.lifecycle import assert_worker_parser_sandbox

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_INPROCESS_PARSER", "true")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = WorkerSettings()
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.load_worker_privileged_storage_secret",
        lambda: "storage-admin-present",
    )
    with pytest.raises(
        JobRepositoryError,
        match="inprocess_parser_forbidden_with_storage_admin_secret",
    ):
        assert_worker_parser_sandbox(settings)


def test_worker_requires_docker_when_inprocess_parser_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default workers fail closed when the parser sandbox Docker CLI is missing."""

    from smart_rag_core.jobs.exceptions import JobRepositoryError
    from smart_rag_worker.lifecycle import assert_worker_parser_sandbox

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("ALLOW_INPROCESS_PARSER", raising=False)
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    settings = WorkerSettings()
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.inprocess_parser_permitted",
        lambda: False,
    )
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.docker_sandbox_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "smart_rag_worker.lifecycle.load_worker_privileged_storage_secret",
        lambda: None,
    )
    with pytest.raises(JobRepositoryError, match="parser_sandbox_docker_required"):
        assert_worker_parser_sandbox(settings)


def test_settings_field_storage_admin_fragment_is_still_forbidden() -> None:
    """A runtime settings **field** containing ``storage_admin`` must still fail."""

    class LeakyRuntimeSettings(BaseModel):
        """Synthetic leak: privileged fragment on a declared field name."""

        supabase_storage_admin_secret: str = "must-fail"  # noqa: S105

    with pytest.raises(AssertionError, match="storage_admin"):
        assert_settings_omit_privileged_secret_names(LeakyRuntimeSettings)


def test_settings_env_alias_storage_admin_fragment_is_still_forbidden() -> None:
    """A runtime settings **env alias** containing ``STORAGE_ADMIN`` must fail."""

    class LeakyAliasSettings(BaseModel):
        """Synthetic leak: privileged fragment on an env alias only."""

        storage_credential: str = Field(
            default="must-fail",
            validation_alias="SUPABASE_STORAGE_ADMIN_SECRET",
        )

    with pytest.raises(AssertionError, match="STORAGE_ADMIN"):
        assert_settings_omit_privileged_secret_names(LeakyAliasSettings)


def test_backend_settings_dump_omits_privileged_env_names() -> None:
    """Loaded runtime settings JSON must not mention privileged secret env names."""

    from smart_rag_core.settings import load_settings

    for settings_cls in RUNTIME_SETTINGS_CLASSES:
        loaded = load_settings(settings_cls)
        dumped = loaded.model_dump_json().upper()
        for fragment in (
            "SUPABASE_AUTH_ADMIN",
            "SUPABASE_STORAGE_ADMIN",
            "SERVICE_ROLE",
            "BOOTSTRAP_MIGRATION",
        ):
            assert fragment not in dumped, (
                f"{settings_cls.__name__} dump has {fragment}"
            )


def test_worker_reads_storage_admin_secret_outside_worker_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker process may load the Storage Admin secret only via isolation."""

    monkeypatch.setenv("SUPABASE_STORAGE_ADMIN_SECRET", "worker-isolated-test-value")
    assert "supabase_storage_admin_secret" not in WorkerSettings.model_fields
    assert load_worker_privileged_storage_secret() == "worker-isolated-test-value"


def test_privileged_loaders_read_their_isolated_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load each privileged secret only through its dedicated settings boundary."""

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_AUTH_ADMIN_SECRET", "auth-admin-test-value")
    monkeypatch.setenv("SUPABASE_STORAGE_ADMIN_SECRET", "storage-admin-test-value")

    auth = load_privileged_auth_settings()
    storage = load_privileged_storage_settings()

    assert str(auth.supabase_url).rstrip("/") == "https://example.supabase.co"
    assert auth.supabase_auth_admin_secret.get_secret_value() == "auth-admin-test-value"
    assert str(storage.supabase_url).rstrip("/") == "https://example.supabase.co"
    assert (
        storage.supabase_storage_admin_secret.get_secret_value()
        == "storage-admin-test-value"
    )
