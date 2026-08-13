"""Typed startup settings for the background worker deployable."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, SecretStr

from smart_rag_core.jobs.limits import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_WORKER_CONCURRENCY,
)
from smart_rag_core.settings.base import SharedSettings, load_settings


class WorkerSettings(SharedSettings):
    """Validated worker configuration for durable job processing.

    Attributes:
        service_name: Stable structured-log service identifier.
        worker_once: Exit after one poll/claim cycle when true.
        supabase_db_url: Worker-role Supabase Postgres DSN.
        job_lease_seconds: Claim and heartbeat lease duration.
        job_heartbeat_interval_seconds: Background heartbeat cadence while
            processing a claimed job.
        job_poll_interval_seconds: Idle delay between queue polls.
        worker_concurrency: Maximum concurrently processed ingestion jobs.
        worker_instance_id: Stable lease owner identifier for this process.
    """

    service_name: ClassVar[Literal["worker"]] = "worker"
    worker_once: bool = Field(
        default=False,
        validation_alias="WORKER_ONCE",
        description="Exit after one poll/claim cycle.",
        json_schema_extra={"security": "public"},
    )
    supabase_db_url: SecretStr | None = Field(
        default=None,
        validation_alias="SUPABASE_DB_URL",
        description="Worker-role Supabase Postgres URL (session/direct).",
        json_schema_extra={"security": "secret"},
    )
    job_lease_seconds: int = Field(
        default=DEFAULT_LEASE_SECONDS,
        validation_alias="JOB_LEASE_SECONDS",
        ge=30,
        le=3600,
        description="Lease duration for claim and heartbeat RPCs.",
        json_schema_extra={"security": "public"},
    )
    job_heartbeat_interval_seconds: int = Field(
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        validation_alias="JOB_HEARTBEAT_INTERVAL_SECONDS",
        ge=10,
        le=900,
        description="Heartbeat interval while processing a claimed job.",
        json_schema_extra={"security": "public"},
    )
    job_poll_interval_seconds: int = Field(
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        validation_alias="JOB_POLL_INTERVAL_SECONDS",
        ge=1,
        le=60,
        description="Idle poll delay when no jobs are claimable.",
        json_schema_extra={"security": "public"},
    )
    worker_concurrency: int = Field(
        default=DEFAULT_WORKER_CONCURRENCY,
        validation_alias="WORKER_CONCURRENCY",
        ge=1,
        le=8,
        description="Maximum concurrently processed ingestion jobs.",
        json_schema_extra={"security": "public"},
    )
    worker_instance_id: str = Field(
        default="worker-local",
        validation_alias="WORKER_INSTANCE_ID",
        min_length=1,
        max_length=256,
        description="Stable lease owner identifier for queue claims.",
        json_schema_extra={"security": "internal"},
    )
    supabase_url: str | None = Field(
        default=None,
        validation_alias="SUPABASE_URL",
        description="Supabase project URL for privileged Storage operations.",
        json_schema_extra={"security": "internal"},
    )
    supabase_storage_admin_secret: SecretStr | None = Field(
        default=None,
        validation_alias="SUPABASE_STORAGE_ADMIN_SECRET",
        description="Storage Admin secret for worker promotion/copy/delete.",
        json_schema_extra={"security": "secret"},
    )
    clamav_host: str = Field(
        default="clamav",
        validation_alias="CLAMAV_HOST",
        description="Private ClamAV daemon hostname.",
        json_schema_extra={"security": "internal"},
    )
    clamav_port: int = Field(
        default=3310,
        validation_alias="CLAMAV_PORT",
        ge=1,
        le=65535,
        description="ClamAV daemon TCP port.",
        json_schema_extra={"security": "internal"},
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
