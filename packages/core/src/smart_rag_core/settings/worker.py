"""Typed startup settings for the background worker deployable."""

from __future__ import annotations

from typing import ClassVar, Literal

from smart_rag_core.settings.base import SharedSettings, load_settings


class WorkerSettings(SharedSettings):
    """Validated worker configuration.

    Attributes:
        service_name: Stable structured-log service identifier. Queue polling,
            leases, and ingestion settings remain owned by later phases.
    """

    service_name: ClassVar[Literal["worker"]] = "worker"


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
