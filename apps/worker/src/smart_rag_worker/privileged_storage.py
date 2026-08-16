"""Isolated Storage Admin secret loader for the worker deployable.

``WorkerSettings`` must not declare ``SUPABASE_STORAGE_ADMIN_SECRET``. Graph
configurable still needs the value at process start, so this module loads it
through a dedicated settings class that is not Shared, Backend, Worker, or
Agent runtime settings.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from smart_rag_core.settings.base import load_settings


class WorkerPrivilegedStorageSettings(BaseSettings):
    """Privileged Storage credential isolated from ``WorkerSettings``.

    Attributes:
        supabase_storage_admin_secret: Optional Storage Admin secret from
            ``SUPABASE_STORAGE_ADMIN_SECRET``. ``None`` when the worker is
            idle without promotion/copy/delete work.
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    supabase_storage_admin_secret: SecretStr | None = Field(
        default=None,
        validation_alias="SUPABASE_STORAGE_ADMIN_SECRET",
        description="Storage Admin secret; never declared on WorkerSettings.",
        json_schema_extra={"security": "secret"},
    )


def load_worker_privileged_storage_secret() -> str | None:
    """Return the Storage Admin secret without attaching it to WorkerSettings.

    Returns:
        Secret string when ``SUPABASE_STORAGE_ADMIN_SECRET`` is set; otherwise
        ``None``.

    Side Effects:
        Reads the process environment through this isolated settings class.
        Does not open a Storage or database connection.
    """

    loaded = load_settings(WorkerPrivilegedStorageSettings)
    if loaded.supabase_storage_admin_secret is None:
        return None
    return loaded.supabase_storage_admin_secret.get_secret_value()
