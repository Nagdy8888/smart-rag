"""Typed startup settings for the privileged Storage Admin boundary."""

from __future__ import annotations

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from smart_rag_core.settings.base import SettingsValidationError


class PrivilegedStorageSettings(BaseSettings):
    """Isolated settings for Storage Admin / service_role object operations.

    This class is **not** part of ``SharedSettings`` and must never be loaded by
    general API health, worker, frontend, or import-time paths. Only modules
    under ``smart_rag_api.storage_admin`` may construct it.

    Attributes:
        supabase_url: Supabase project URL for Storage REST calls.
        supabase_storage_admin_secret: Broad Storage credential from
            ``SUPABASE_STORAGE_ADMIN_SECRET`` (typically service_role equivalent).
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    supabase_url: AnyHttpUrl = Field(
        validation_alias="SUPABASE_URL",
        description="Supabase project URL for privileged Storage Admin calls.",
        json_schema_extra={"security": "internal"},
    )
    supabase_storage_admin_secret: SecretStr = Field(
        validation_alias="SUPABASE_STORAGE_ADMIN_SECRET",
        description="Storage Admin secret; never loaded by SharedSettings.",
        json_schema_extra={"security": "secret"},
    )


def load_privileged_storage_settings() -> PrivilegedStorageSettings:
    """Load privileged Storage Admin settings from the process environment.

    Returns:
        Validated privileged settings.

    Raises:
        SettingsValidationError: When required secrets are missing or invalid.

    Side Effects:
        Reads ``SUPABASE_STORAGE_ADMIN_SECRET`` only inside this boundary.
    """

    from pydantic import ValidationError

    try:
        return PrivilegedStorageSettings.model_validate({})
    except ValidationError as error:
        issues = sorted(
            {
                f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
                for item in error.errors(include_url=False, include_context=False)
            }
        )
        summary = ", ".join(issues) if issues else "unknown validation error"
        raise SettingsValidationError(
            f"Invalid PrivilegedStorageSettings configuration ({summary})"
        ) from None
