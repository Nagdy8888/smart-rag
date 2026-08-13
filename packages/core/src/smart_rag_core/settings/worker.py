"""Typed startup settings for the background worker deployable."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from smart_rag_core.settings.base import SharedSettings, load_settings


class WorkerSettings(SharedSettings):
    """Validated worker configuration.

    Attributes:
        service_name: Stable structured-log service identifier. Queue polling,
            leases, and ingestion settings remain owned by later phases.
        worker_once: Whether the foundation process exits after one startup
            probe. Used by tests and administrative smoke checks.
    """

    service_name: ClassVar[Literal["worker"]] = "worker"
    worker_once: bool = Field(
        default=False,
        validation_alias="WORKER_ONCE",
        description="Exit after one foundation startup probe.",
        json_schema_extra={"security": "public"},
    )


def load_worker_settings() -> WorkerSettings:
    """Load validated worker settings from the process environment.

    Returns:
        Validated worker settings.

    Raises:
        SettingsValidationError: If startup configuration is invalid.

    Side Effects:
        Reads environment variables through the shared settings boundary.
    """

    return load_settings(WorkerSettings)
