"""Typed startup settings for the FastAPI backend deployable."""

from __future__ import annotations

from typing import ClassVar, Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator

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
        lightrag_db_url: Optional session/direct Postgres URL for the runtime
            LightRAG adapter as ``app_lightrag``. Secret. When unset, the
            graph adapter stays unconfigured. Never a schema-admin DSN.
        cors_allow_origins: Comma-separated exact browser origins from
            ``CORS_ALLOW_ORIGINS``. Wildcards are rejected. Default local
            frontend origins.
        api_version: Public API major.minor.patch from ``API_VERSION``.
        sse_schema_version: SSE schema label from ``SSE_SCHEMA_VERSION``.
            Packet 6 owns handshake enforcement; this packet only publishes
            the value on ``/api/meta``.
        min_client_version: Minimum client version from
            ``MIN_CLIENT_VERSION``. Packet 6 owns upgrade rejection.
        retrieval_cache_result_ttl_seconds: Hybrid ID/rank cache TTL.
        retrieval_cache_profile_ttl_seconds: Profile/embedding cache TTL.
        request_max_body_bytes: Maximum JSON/body size in bytes.
        valkey_timeout_seconds: Bounded Valkey connect/command timeout.
        rate_limit_retry_after_seconds: ``Retry-After`` on 429/503 limiter
            responses.
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
        default=AnyHttpUrl("http://127.0.0.1:54321"),
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
    lightrag_db_url: SecretStr | None = Field(
        default=None,
        validation_alias="LIGHTRAG_DB_URL",
        description=(
            "Session/direct Postgres URL for the LightRAG runtime adapter. "
            "Role app_lightrag via SET ROLE. Never schema-admin."
        ),
        json_schema_extra={"security": "secret"},
    )
    cors_allow_origins: str = Field(
        default="http://127.0.0.1:3000,http://localhost:3000",
        validation_alias="CORS_ALLOW_ORIGINS",
        min_length=0,
        max_length=4096,
        description="Comma-separated exact CORS origins. Wildcards forbidden.",
        json_schema_extra={"security": "public"},
    )
    api_version: str = Field(
        default="0.1.0",
        validation_alias="API_VERSION",
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
        description="Public API version published by /api/meta.",
        json_schema_extra={"security": "public"},
    )
    sse_schema_version: str = Field(
        default="1",
        validation_alias="SSE_SCHEMA_VERSION",
        min_length=1,
        max_length=32,
        pattern=r"^[0-9A-Za-z._-]+$",
        description="SSE schema version for packet 6 handshake.",
        json_schema_extra={"security": "public"},
    )
    min_client_version: str = Field(
        default="0.1.0",
        validation_alias="MIN_CLIENT_VERSION",
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
        description="Minimum client version advertised by /api/meta.",
        json_schema_extra={"security": "public"},
    )
    retrieval_cache_result_ttl_seconds: int = Field(
        default=30,
        validation_alias="RETRIEVAL_CACHE_RESULT_TTL_SECONDS",
        ge=1,
        le=300,
        description="TTL in seconds for ID/rank retrieval cache entries.",
        json_schema_extra={"security": "public"},
    )
    retrieval_cache_profile_ttl_seconds: int = Field(
        default=300,
        validation_alias="RETRIEVAL_CACHE_PROFILE_TTL_SECONDS",
        ge=1,
        le=3600,
        description="TTL in seconds for profile/embedding cache entries.",
        json_schema_extra={"security": "public"},
    )
    request_max_body_bytes: int = Field(
        default=1_048_576,
        validation_alias="REQUEST_MAX_BODY_BYTES",
        ge=1024,
        le=16_777_216,
        description="Maximum accepted HTTP body size in bytes.",
        json_schema_extra={"security": "public"},
    )
    valkey_timeout_seconds: float = Field(
        default=0.2,
        validation_alias="VALKEY_TIMEOUT_SECONDS",
        ge=0.05,
        le=2.0,
        description="Valkey connect and command timeout in seconds.",
        json_schema_extra={"security": "public"},
    )
    rate_limit_retry_after_seconds: int = Field(
        default=60,
        validation_alias="RATE_LIMIT_RETRY_AFTER_SECONDS",
        ge=1,
        le=3600,
        description="Retry-After seconds for limiter 429/503 responses.",
        json_schema_extra={"security": "public"},
    )

    @field_validator("cors_allow_origins")
    @classmethod
    def reject_wildcard_cors(cls, value: str) -> str:
        """Reject wildcard CORS origins.

        Args:
            value: Raw comma-separated origin list.

        Returns:
            The original string when every origin is exact.

        Raises:
            ValueError: If ``*`` appears as an origin token.
        """

        origins = [item.strip() for item in value.split(",") if item.strip()]
        if any(origin == "*" for origin in origins):
            raise ValueError("CORS wildcard origins are forbidden")
        return value

    @model_validator(mode="after")
    def require_exact_cors_origins(self) -> Self:
        """Require parsed origins to remain exact HTTP(S) origins.

        Returns:
            This settings instance.

        Raises:
            ValueError: If an origin is empty after parse or uses a wildcard
                scheme/host.
        """

        for origin in self.parsed_cors_origins():
            lowered = origin.casefold()
            if (
                "*" in origin
                or lowered.startswith("http://*")
                or lowered.startswith("https://*")
            ):
                raise ValueError("CORS wildcard origins are forbidden")
        return self

    def parsed_cors_origins(self) -> tuple[str, ...]:
        """Return exact CORS origins with no wildcard credentials pairing.

        Returns:
            Distinct origin strings in configuration order.
        """

        seen: set[str] = set()
        ordered: list[str] = []
        for item in self.cors_allow_origins.split(","):
            origin = item.strip()
            if not origin or origin in seen:
                continue
            seen.add(origin)
            ordered.append(origin)
        return tuple(ordered)


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
