"""Shared typed configuration primitives for Smart RAG deployables.

Settings are instantiated only by explicit startup loaders. Environment
variables therefore cannot construct provider or database clients at import
time, and validation failures are converted to messages that omit input values.
"""

from __future__ import annotations

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
            ``MOCK_MODEL_MODE``. Public, secure default ``true``.
        log_level: Structured logging threshold from ``LOG_LEVEL``. Public,
            default ``INFO``.
        openai_api_key: Provider credential from ``OPENAI_API_KEY``. Secret and
            optional only while mock mode is enabled.
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
        description="Use deterministic model fixtures and deny OpenAI network access.",
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


SettingsT = TypeVar("SettingsT", bound=SharedSettings)


def load_settings(settings_type: type[SettingsT]) -> SettingsT:
    """Load and validate one deployable's environment configuration.

    Args:
        settings_type: Concrete settings class for the starting deployable.

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
