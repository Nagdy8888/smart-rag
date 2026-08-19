"""Shared typed configuration primitives for Smart RAG deployables.

Settings are instantiated only by explicit startup loaders. Environment
variables therefore cannot construct provider or database clients at import
time, and validation failures are converted to messages that omit input values.
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Self, TypeVar

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported deployment environment names."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Supported application log thresholds."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SettingsValidationError(RuntimeError):
    """Report invalid startup configuration without exposing source values."""


class SharedSettings(BaseSettings):
    """Configuration shared by the backend, worker, and agent deployables.

    Attributes:
        app_env: Deployment environment from ``APP_ENV``. Public, default
            ``local``.
        mock_model_mode: Whether model work uses frozen fixtures from
            ``MOCK_MODEL_MODE``. Public, secure default ``true``. Staging and
            production reject ``true``.
        allow_test_identity: Whether ``X-Test-*`` identity headers may mint a
            caller from ``ALLOW_TEST_IDENTITY``. Public, secure default
            ``false``. Staging and production reject ``true``.
        log_level: Structured logging threshold from ``LOG_LEVEL``. Public,
            default ``INFO``.
        openai_api_key: Provider credential from ``OPENAI_API_KEY``. Secret and
            optional only while mock mode is enabled.
        langsmith_tracing: Whether LangSmith export is enabled from
            ``LANGSMITH_TRACING``. Public, secure default ``false``.
        langsmith_api_key: LangSmith credential from ``LANGSMITH_API_KEY``.
            Secret; required when tracing is enabled.
        langsmith_project: LangSmith project name from ``LANGSMITH_PROJECT``.
            Public, default ``smart-rag``.
        langsmith_endpoint: Optional LangSmith API URL from
            ``LANGSMITH_ENDPOINT``. Internal.
        subprocessor_matrix_verified: Signed LangSmith/Vercel org-matrix
            verification from ``SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED``.
            Public, secure default ``false``.
        mock_fixture_id: Frozen fixture identifier from
            ``MOCK_MODEL_FIXTURE_ID``. Internal, default
            ``phase-1-foundation-v1``.
        model_input_max_chars: Maximum model input size from
            ``MODEL_INPUT_MAX_CHARS``. Public, bounded from 1 through 65536,
            default 16384 characters.
        valkey_limits_url: Rate-limit Valkey URL from ``VALKEY_LIMITS_URL``.
            Secret because it can contain credentials.
        valkey_cache_url: Cache Valkey URL from ``VALKEY_CACHE_URL``. Secret
            because it can contain credentials.
        paradedb_url: Derived-index database URL from ``PARADEDB_URL``. Secret
            because it can contain credentials.
        crawl_proxy_url: Internal crawl-proxy endpoint from
            ``CRAWL_PROXY_URL``. Internal, optional in the foundation phase.
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: Environment = Field(
        default=Environment.LOCAL,
        validation_alias="APP_ENV",
        description="Deployment environment.",
        json_schema_extra={"security": "public"},
    )
    mock_model_mode: bool = Field(
        default=True,
        validation_alias="MOCK_MODEL_MODE",
        description=(
            "Use deterministic model fixtures and deny OpenAI network access. "
            "Forbidden when APP_ENV is staging or production."
        ),
        json_schema_extra={"security": "public"},
    )
    allow_test_identity: bool = Field(
        default=False,
        validation_alias="ALLOW_TEST_IDENTITY",
        description=(
            "Permit X-Test-* identity headers together with APP_ENV=test. "
            "Production images omit this variable. Forbidden when APP_ENV is "
            "staging or production."
        ),
        json_schema_extra={"security": "public"},
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        validation_alias="LOG_LEVEL",
        description="Minimum structured log level.",
        json_schema_extra={"security": "public"},
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        description="OpenAI credential required only outside mock mode.",
        json_schema_extra={"security": "secret"},
    )
    langsmith_tracing: bool = Field(
        default=False,
        validation_alias="LANGSMITH_TRACING",
        description="Export redacted model-call traces to LangSmith.",
        json_schema_extra={"security": "public"},
    )
    langsmith_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="LANGSMITH_API_KEY",
        description="LangSmith credential required when tracing is enabled.",
        json_schema_extra={"security": "secret"},
    )
    langsmith_project: str = Field(
        default="smart-rag",
        validation_alias="LANGSMITH_PROJECT",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="LangSmith project that receives redacted traces.",
        json_schema_extra={"security": "public"},
    )
    langsmith_endpoint: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="LANGSMITH_ENDPOINT",
        description="Optional LangSmith API URL; unset uses the hosted default.",
        json_schema_extra={"security": "internal"},
    )
    subprocessor_matrix_verified: bool = Field(
        default=False,
        validation_alias="SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED",
        description=(
            "True only after the signed LangSmith/Vercel org matrix is "
            "verified. Real company content cannot enable tracing until then."
        ),
        json_schema_extra={"security": "public"},
    )
    mock_fixture_id: str = Field(
        default="phase-1-foundation-v1",
        validation_alias="MOCK_MODEL_FIXTURE_ID",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Frozen mock-model fixture identifier.",
        json_schema_extra={"security": "internal"},
    )
    model_input_max_chars: int = Field(
        default=16_384,
        validation_alias="MODEL_INPUT_MAX_CHARS",
        ge=1,
        le=65_536,
        description="Maximum characters accepted by the model gateway.",
        json_schema_extra={"security": "public"},
    )
    valkey_limits_url: SecretStr | None = Field(
        default=None,
        validation_alias="VALKEY_LIMITS_URL",
        description="Authenticated private rate-limit Valkey URL.",
        json_schema_extra={"security": "secret"},
    )
    valkey_cache_url: SecretStr | None = Field(
        default=None,
        validation_alias="VALKEY_CACHE_URL",
        description="Authenticated private cache Valkey URL.",
        json_schema_extra={"security": "secret"},
    )
    paradedb_url: SecretStr | None = Field(
        default=None,
        validation_alias="PARADEDB_URL",
        description="Private derived-index database URL.",
        json_schema_extra={"security": "secret"},
    )
    crawl_proxy_url: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="CRAWL_PROXY_URL",
        description="Private deny-by-default crawl-proxy URL.",
        json_schema_extra={"security": "internal"},
    )

    @model_validator(mode="after")
    def require_provider_key_outside_mock_mode(self) -> Self:
        """Require a provider credential when deterministic fixtures are disabled.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: If real-model mode has no OpenAI credential.
        """

        if not self.mock_model_mode and self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when MOCK_MODEL_MODE=false")
        return self

    @model_validator(mode="after")
    def reject_unsafe_hosted_environment_flags(self) -> Self:
        """Fail closed when staging or production enable mock or test identity.

        ``APP_ENV=test`` is a distinct environment, not a production label.
        Hosted environments must not start with mock fixtures or the HTTP
        identity bypass.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: If mock mode or test identity is enabled in staging
                or production.
        """

        if self.app_env not in {Environment.STAGING, Environment.PRODUCTION}:
            return self
        if self.mock_model_mode:
            raise ValueError(
                "MOCK_MODEL_MODE must be false when APP_ENV is staging or production"
            )
        if self.allow_test_identity:
            raise ValueError(
                "ALLOW_TEST_IDENTITY is forbidden when APP_ENV is staging or production"
            )
        return self

    @model_validator(mode="after")
    def require_langsmith_key_when_tracing(self) -> Self:
        """Require a LangSmith credential when trace export is enabled.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: If tracing is enabled without ``LANGSMITH_API_KEY``.
        """

        if self.langsmith_tracing and self.langsmith_api_key is None:
            raise ValueError(
                "LANGSMITH_API_KEY is required when LANGSMITH_TRACING=true"
            )
        return self

    def allows_unsigned_local_live_providers(self) -> bool:
        """Return whether local live OpenAI/LangSmith keys may run without org rows.

        ``APP_ENV=local`` plus ``MOCK_MODEL_MODE=false`` is an operator waiver
        for gitignored keys. It does **not** mark the OpenAI or LangSmith org
        matrices verified. Staging and production still require
        ``SMART_RAG_SUBPROCESSOR_MATRIX_VERIFIED``.

        Returns:
            True only for local non-mock processes.
        """

        return self.app_env is Environment.LOCAL and not self.mock_model_mode

    def apply_langsmith_sdk_flags(self) -> dict[str, str]:
        """Write LangSmith SDK process flags from already-validated settings.

        Hide-input and hide-output are always enabled so wrapper-generated
        child spans cannot export Responses or embedding bodies. Tracing is
        forced off unless this instance enabled it, so a leftover shell
        variable cannot outrank the typed contract.

        Returns:
            Applied flag names and non-secret values. The API key is omitted.

        Side Effects:
            Mutates ``LANGSMITH_*`` process environment keys consumed by the
            pinned LangSmith SDK. Does not open a network connection.
        """

        os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
        os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
        applied: dict[str, str] = {
            "LANGSMITH_HIDE_INPUTS": "true",
            "LANGSMITH_HIDE_OUTPUTS": "true",
            "LANGSMITH_TRACING": "false",
            "LANGSMITH_PROJECT": self.langsmith_project,
        }
        if not self.langsmith_tracing or self.langsmith_api_key is None:
            os.environ["LANGSMITH_TRACING"] = "false"
            return applied
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key.get_secret_value()
        os.environ["LANGSMITH_PROJECT"] = self.langsmith_project
        applied["LANGSMITH_TRACING"] = "true"
        if self.langsmith_endpoint is not None:
            endpoint = str(self.langsmith_endpoint).rstrip("/")
            os.environ["LANGSMITH_ENDPOINT"] = endpoint
            applied["LANGSMITH_ENDPOINT"] = endpoint
        return applied


def snapshot_process_environ() -> dict[str, str]:
    """Copy process environment for sandbox filtering.

    Structured-table workers must not inherit provider secrets. This
    snapshot is the only process-environment read used by the table
    executor.

    Returns:
        Shallow copy of the current process environment.
    """

    return dict(os.environ)


def get_process_environ(name: str, default: str | None = None) -> str | None:
    """Return one process environment value from the settings boundary.

    Args:
        name: Environment variable name.
        default: Value when ``name`` is unset. ``None`` means missing.

    Returns:
        The stored value, ``default`` when unset, or ``None``.
    """

    value = os.environ.get(name, default)
    if value is None:
        return None
    return value


def set_process_environ(name: str, value: str) -> None:
    """Set one process environment value from the settings boundary.

    Args:
        name: Environment variable name.
        value: Value to store. Callers must not log secrets.
    """

    os.environ[name] = value


def pop_process_environ(name: str) -> None:
    """Remove one process environment key when present.

    Args:
        name: Environment variable name to delete.
    """

    os.environ.pop(name, None)


def setdefault_process_environ(name: str, value: str) -> str:
    """Set one process environment value only when the key is missing.

    Args:
        name: Environment variable name.
        value: Value to store when unset. Callers must not log secrets.

    Returns:
        The existing value, or ``value`` when the key was missing.
    """

    return os.environ.setdefault(name, value)


SettingsT = TypeVar("SettingsT", bound=BaseSettings)


def load_settings(settings_type: type[SettingsT]) -> SettingsT:
    """Load and validate one centralized environment configuration model.

    Args:
        settings_type: Concrete settings class for a deployable or bounded
            administrative operation.

    Returns:
        A validated settings instance.

    Raises:
        SettingsValidationError: If any field is invalid. The exception lists
            field paths and error categories only; source values are omitted.

    Side Effects:
        Reads process environment variables through Pydantic Settings.
    """

    try:
        return settings_type()
    except ValidationError as error:
        issues = sorted(
            {
                f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
                for item in error.errors(include_url=False, include_context=False)
            }
        )
        summary = ", ".join(issues) if issues else "unknown validation error"
        raise SettingsValidationError(
            f"Invalid {settings_type.__name__} configuration ({summary})"
        ) from None
