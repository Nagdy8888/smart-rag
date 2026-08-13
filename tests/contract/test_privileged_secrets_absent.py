"""Prove privileged/bootstrap secrets are absent from general runtime settings."""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from smart_rag_api.auth_admin.settings import load_privileged_auth_settings
from smart_rag_api.storage_admin.settings import load_privileged_storage_settings
from smart_rag_core.settings import BackendSettings, SharedSettings, WorkerSettings
from smart_rag_core.settings.agents import AgentSettings

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
    """Return lowercased model field names for one settings class."""

    return {name.lower() for name in settings_cls.model_fields}


def _alias_names(settings_cls: type[BaseModel]) -> set[str]:
    """Return uppercased validation aliases for one settings class."""

    aliases: set[str] = set()
    for field in settings_cls.model_fields.values():
        alias = field.validation_alias
        if isinstance(alias, str):
            aliases.add(alias.upper())
    return aliases


def test_privileged_secrets_absent_from_runtime_settings() -> None:
    """Shared/Backend/Worker/Agent settings must not declare privileged secrets."""

    for settings_cls in (
        SharedSettings,
        BackendSettings,
        WorkerSettings,
        AgentSettings,
    ):
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


def test_backend_settings_dump_omits_privileged_env_names() -> None:
    """Loaded BackendSettings JSON must not mention privileged secret env names."""

    from smart_rag_core.settings import load_settings

    loaded = load_settings(BackendSettings)
    dumped = loaded.model_dump_json().upper()
    for fragment in (
        "SUPABASE_AUTH_ADMIN",
        "SUPABASE_STORAGE_ADMIN",
        "SERVICE_ROLE",
        "BOOTSTRAP_MIGRATION",
    ):
        assert fragment not in dumped


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
