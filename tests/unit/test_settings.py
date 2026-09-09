"""Unit tests for centralized deployable settings validation."""

from __future__ import annotations

import pytest
from smart_rag_core.settings import (
    AgentSettings,
    BackendSettings,
    Environment,
    JwksRolloverSettings,
    SettingsValidationError,
    SharedSettings,
    WorkerSettings,
    load_backend_settings,
    load_jwks_rollover_settings,
    load_worker_settings,
)


def configure_hosted_backend_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app_env: str = "production",
) -> None:
    """Set the minimum valid staging/production backend environment.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        app_env: ``staging`` or ``production``.
    """

    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("MOCK_MODEL_MODE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-unit-fixture-not-real")
    monkeypatch.setenv("VALKEY_LIMITS_URL", "redis://:unit@127.0.0.1:6379/0")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "false")


def test_deployable_settings_are_typed_and_share_secure_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All deployable settings inherit deterministic mock-mode defaults."""

    monkeypatch.delenv("APP_ENV", raising=False)
    backend = BackendSettings()
    worker = WorkerSettings()
    agents = AgentSettings()

    assert backend.app_env is Environment.LOCAL
    assert backend.mock_model_mode is True
    assert backend.allow_test_identity is False
    assert backend.service_name == "backend"
    assert worker.service_name == "worker"
    assert agents.service_name == "agents"
    assert agents.langgraph_studio_live_enabled is False
    assert agents.langgraph_studio_access_token is None
    assert not issubclass(AgentSettings, BackendSettings)


def test_agent_studio_live_token_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Studio live JWT stays on AgentSettings and never appears in repr."""

    canary = "studio-live-settings-canary-token"
    monkeypatch.setenv("LANGGRAPH_STUDIO_LIVE_ENABLED", "true")
    monkeypatch.setenv("LANGGRAPH_STUDIO_ACCESS_TOKEN", canary)
    settings = AgentSettings()
    assert settings.langgraph_studio_live_enabled is True
    assert settings.langgraph_studio_access_token is not None
    assert settings.langgraph_studio_access_token.get_secret_value() == canary
    assert canary not in repr(settings)
    assert canary not in str(settings)


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


def test_local_backend_requires_explicit_supabase_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Laptop runtime fails closed when ``SUPABASE_URL`` is omitted."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(SettingsValidationError) as caught:
        load_backend_settings()
    assert "127.0.0.1" not in str(caught.value)
    assert "supabase.co" not in str(caught.value)


def test_test_env_injects_local_supabase_fixture_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``APP_ENV=test`` may omit ``SUPABASE_URL`` and uses the local fixture."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    settings = load_backend_settings()
    assert str(settings.supabase_url).rstrip("/") == "http://127.0.0.1:54321"


def test_wildcard_cors_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentialed wildcard CORS cannot be configured."""

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example,*")
    with pytest.raises(SettingsValidationError):
        load_backend_settings()


def test_backend_cache_ttl_and_api_version_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Packet 5 cache TTLs and handshake versions have signed defaults."""

    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    settings = BackendSettings()
    assert settings.retrieval_cache_result_ttl_seconds == 30
    assert settings.retrieval_cache_profile_ttl_seconds == 300
    assert settings.api_version == "0.1.0"
    assert settings.sse_schema_version == "1"
    assert settings.parsed_cors_origins() == (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3010",
        "http://localhost:3010",
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


def test_checkpoint_pooler_dsn_fails_closed_without_leaking_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transaction-pooler checkpoint URLs fail before a paid run can start."""

    secret = "super-secret-pooler-password"  # noqa: S105 - inert fixture
    host = "aws-0-us-east-1.pooler.supabase.com"
    monkeypatch.setenv(
        "LANGGRAPH_CHECKPOINT_URL",
        f"postgresql://unit:{secret}@{host}:6543/postgres",
    )
    with pytest.raises(SettingsValidationError) as exc_info:
        load_backend_settings()
    text = str(exc_info.value)
    assert secret not in text
    assert host not in text
    assert "postgresql://" not in text


def test_session_checkpoint_dsn_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct/session checkpoint URLs remain valid."""

    monkeypatch.setenv(
        "LANGGRAPH_CHECKPOINT_URL",
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    )
    settings = load_backend_settings()
    assert (
        settings.resolved_checkpoint_dsn()
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


def test_production_and_staging_reject_mock_mode_and_test_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hosted environments fail closed on mock fixtures and test bypass."""

    for app_env in ("staging", "production"):
        configure_hosted_backend_env(monkeypatch, app_env=app_env)
        monkeypatch.setenv("MOCK_MODEL_MODE", "true")
        with pytest.raises(SettingsValidationError):
            load_backend_settings()
        configure_hosted_backend_env(monkeypatch, app_env=app_env)
        monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
        with pytest.raises(SettingsValidationError):
            load_backend_settings()


def test_local_and_test_keep_mock_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local and test may keep ``MOCK_MODEL_MODE=true`` and omit Valkey."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    monkeypatch.delenv("VALKEY_LIMITS_URL", raising=False)
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "false")
    local = load_backend_settings()
    assert local.app_env is Environment.LOCAL
    assert local.mock_model_mode is True
    assert local.allow_test_identity is False

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    test_settings = load_backend_settings()
    assert test_settings.app_env is Environment.TEST
    assert test_settings.allow_test_identity is True


def test_hosted_environments_reject_langsmith_export_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Staging and production cannot export raw LangSmith I/O."""

    configure_hosted_backend_env(monkeypatch, app_env="production")
    monkeypatch.setenv("LANGSMITH_EXPORT_IO", "true")
    with pytest.raises(SettingsValidationError):
        load_backend_settings()


def test_hosted_environments_require_https_non_loopback_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Staging and production reject loopback and non-HTTPS CORS origins."""

    configure_hosted_backend_env(monkeypatch, app_env="production")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://127.0.0.1:3000")
    with pytest.raises(SettingsValidationError):
        load_backend_settings()

    configure_hosted_backend_env(monkeypatch, app_env="staging")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://localhost:3000")
    with pytest.raises(SettingsValidationError):
        load_backend_settings()

    configure_hosted_backend_env(monkeypatch, app_env="production")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example")
    settings = load_backend_settings()
    assert settings.parsed_cors_origins() == ("https://app.example",)


def test_hosted_environments_require_valkey_limits_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unconfigured Valkey cannot start a hosted public listener."""

    configure_hosted_backend_env(monkeypatch, app_env="production")
    monkeypatch.delenv("VALKEY_LIMITS_URL", raising=False)
    with pytest.raises(SettingsValidationError):
        load_backend_settings()

    configure_hosted_backend_env(monkeypatch, app_env="staging")
    settings = load_backend_settings()
    assert settings.valkey_limits_url is not None


def test_local_live_providers_waive_org_matrix_without_marking_it_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local mock-off keys are an operator waiver, not org-matrix verification."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("MOCK_MODEL_MODE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-unsigned-not-an-org-row")
    monkeypatch.delenv("SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED", raising=False)
    local = SharedSettings()
    assert local.allows_unsigned_local_live_providers() is True
    assert local.subprocessor_matrix_verified is False

    monkeypatch.setenv("APP_ENV", "staging")
    staging = SharedSettings()
    assert staging.allows_unsigned_local_live_providers() is False
    assert staging.app_env is Environment.STAGING


def test_allow_inprocess_parser_rejected_outside_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ALLOW_INPROCESS_PARSER is valid only when APP_ENV=test."""

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ALLOW_INPROCESS_PARSER", "true")
    monkeypatch.setenv("MOCK_MODEL_MODE", "true")
    with pytest.raises(SettingsValidationError):
        load_worker_settings()

    monkeypatch.setenv("APP_ENV", "test")
    settings = load_worker_settings()
    assert settings.allow_inprocess_parser is True
    assert settings.app_env is Environment.TEST
