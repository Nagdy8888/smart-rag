"""Typed startup settings for the privileged Auth Admin boundary."""

from __future__ import annotations

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from smart_rag_core.settings.base import SettingsValidationError


class PrivilegedAuthSettings(BaseSettings):
    """Isolated settings for Auth Admin / service_role operations.

    This class is **not** part of ``SharedSettings`` and must never be loaded by
    general API health, worker, frontend, or import-time paths. Only modules
    under ``smart_rag_api.auth_admin`` may construct it.

    Attributes:
        supabase_url: Supabase project URL for Auth Admin REST calls.
        supabase_auth_admin_secret: ``service_role`` or dedicated Auth Admin
            secret from ``SUPABASE_AUTH_ADMIN_SECRET``.
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    supabase_url: AnyHttpUrl = Field(
        validation_alias="SUPABASE_URL",
        description="Supabase project URL for privileged Auth Admin calls.",
        json_schema_extra={"security": "internal"},
    )
    supabase_auth_admin_secret: SecretStr = Field(
        validation_alias="SUPABASE_AUTH_ADMIN_SECRET",
        description="Auth Admin secret; never loaded by SharedSettings.",
        json_schema_extra={"security": "secret"},
    )


def load_privileged_auth_settings() -> PrivilegedAuthSettings:
    """Load privileged Auth Admin settings from the process environment.

    Returns:
        Validated privileged settings.

    Raises:
        SettingsValidationError: When required secrets are missing or invalid.

    Side Effects:
        Reads ``SUPABASE_AUTH_ADMIN_SECRET`` only inside this boundary.
    """

    from pydantic import ValidationError

    try:
        return PrivilegedAuthSettings()
    except ValidationError as error:
        issues = sorted(
            {
                f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
                for item in error.errors(include_url=False, include_context=False)
            }
        )
        summary = ", ".join(issues) if issues else "unknown validation error"
        raise SettingsValidationError(
            f"Invalid PrivilegedAuthSettings configuration ({summary})"
        ) from None
