"""Typed settings for bounded administrative proof operations."""

from __future__ import annotations

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from smart_rag_core.settings.base import load_settings


class JwksRolloverSettings(BaseSettings):
    """Credentials and endpoints for the destructive managed rollover proof.

    Attributes:
        supabase_access_token: Short-lived Management API bearer token.
        supabase_project_ref: Managed Supabase project reference.
        supabase_managed_url: Managed project API origin.
        supabase_anon_key: Public Auth API key treated as secret in process
            representations to avoid accidental credential logging.
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    supabase_access_token: SecretStr = Field(
        validation_alias="SUPABASE_ACCESS_TOKEN",
        description="Short-lived Supabase Management API access token.",
        json_schema_extra={"security": "secret"},
    )
    supabase_project_ref: str = Field(
        validation_alias="SUPABASE_PROJECT_REF",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Managed Supabase project reference.",
        json_schema_extra={"security": "internal"},
    )
    supabase_managed_url: AnyHttpUrl = Field(
        validation_alias="SUPABASE_MANAGED_URL",
        description="Managed Supabase project API origin.",
        json_schema_extra={"security": "internal"},
    )
    supabase_anon_key: SecretStr = Field(
        validation_alias="SUPABASE_ANON_KEY",
        description="Publishable Auth API key used by the rollover proof.",
        json_schema_extra={"security": "secret"},
    )


def load_jwks_rollover_settings() -> JwksRolloverSettings:
    """Load sanitized settings for the managed JWKS rollover proof.

    Returns:
        Validated rollover settings.

    Raises:
        SettingsValidationError: If a required value is missing or invalid.

    Side Effects:
        Reads process environment through Pydantic Settings. No provider call
        or signing-key mutation occurs during loading.
    """

    return load_settings(JwksRolloverSettings)
