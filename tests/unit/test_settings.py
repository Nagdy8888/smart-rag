"""Unit tests for centralized deployable settings validation."""

from __future__ import annotations

import pytest
from smart_rag_core.settings import (
    AgentSettings,
    BackendSettings,
    Environment,
    SettingsValidationError,
    WorkerSettings,
    load_backend_settings,
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
