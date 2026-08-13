"""Typed startup settings for the FastAPI backend deployable."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import AnyHttpUrl, Field, SecretStr

from smart_rag_core.settings.base import SharedSettings, load_settings


class BackendSettings(SharedSettings):
    """Validated backend configuration.

    Attributes:
        service_name: Stable structured-log service identifier.
        bind_host: HTTP bind address from ``API_BIND_HOST``. Public, default
            ``0.0.0.0``.
        bind_port: HTTP bind port from ``API_BIND_PORT``. Public, default
            ``8000``.
        supabase_url: Supabase project URL from ``SUPABASE_URL``. Public.
        supabase_jwt_audience: Required JWT audience from
            ``SUPABASE_JWT_AUDIENCE``. Default ``authenticated``.
        jwks_cache_seconds: JWKS cache TTL from ``JWKS_CACHE_SECONDS``; max
            600 seconds.
        supabase_db_url: Transaction-pooled Postgres URL for profile reads as
            ``app_api``. Secret.
    """

    service_name: ClassVar[Literal["backend"]] = "backend"
    bind_host: str = Field(
        default="0.0.0.0",  # noqa: S104 - container HTTP listener default
        validation_alias="API_BIND_HOST",
        min_length=1,
        max_length=255,
        description="Backend HTTP bind address.",
        json_schema_extra={"security": "public"},
    )
    bind_port: int = Field(
        default=8000,
        validation_alias="API_BIND_PORT",
        ge=1,
        le=65535,
        description="Backend HTTP bind port.",
        json_schema_extra={"security": "public"},
    )
    supabase_url: AnyHttpUrl = Field(
        default="http://127.0.0.1:54321",
        validation_alias="SUPABASE_URL",
        description="Supabase project URL for JWKS discovery.",
        json_schema_extra={"security": "public"},
    )
    supabase_jwt_audience: str = Field(
        default="authenticated",
        validation_alias="SUPABASE_JWT_AUDIENCE",
        min_length=1,
        max_length=128,
        description="Required JWT aud claim for access tokens.",
        json_schema_extra={"security": "public"},
    )
    jwks_cache_seconds: int = Field(
        default=600,
        validation_alias="JWKS_CACHE_SECONDS",
        ge=1,
        le=600,
        description="JWKS cache TTL in seconds (maximum 600).",
        json_schema_extra={"security": "public"},
    )
    supabase_db_url: SecretStr | None = Field(
        default=None,
        validation_alias="SUPABASE_DB_URL",
        description="Postgres URL for server-side profile reads as app_api.",
        json_schema_extra={"security": "secret"},
    )


def load_backend_settings() -> BackendSettings:
    """Load validated backend settings from the process environment.

    Returns:
        Validated backend settings.

    Raises:
        SettingsValidationError: If startup configuration is invalid.

    Side Effects:
        Reads environment variables through the shared settings boundary.
    """

    return load_settings(BackendSettings)
