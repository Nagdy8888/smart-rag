"""Ingestion queue repository with idempotent enqueue and leased lifecycle."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.jobs.admission import JobAdmissionService
from smart_rag_core.jobs.backoff import compute_retry_delay_seconds
from smart_rag_core.jobs.exceptions import (
    JobLeaseError,
    JobNotFoundError,
    JobRepositoryError,
)
from smart_rag_core.jobs.limits import DEFAULT_MAX_JOB_ATTEMPTS
from smart_rag_core.schema.enums import JobErrorCategory, JobPriority, JobStatus
from smart_rag_core.schema.tables import IngestionJobRecord


class IngestionJobRepository:
    """Worker-facing ingestion job persistence using Supabase RPC helpers."""

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> None:
        """Bind a worker connection and lease parameters.

        Args:
            connection: Postgres connection operating as ``app_worker``.
            lease_owner: Stable worker instance identifier used in claims.
            lease_seconds: Lease duration passed to claim/heartbeat RPCs.
        """

        self._connection = connection
        self._lease_owner = lease_owner
        self._lease_seconds = lease_seconds
        self._admission = JobAdmissionService(connection)

    @property
    def admission(self) -> JobAdmissionService:
        """Return the admission helper bound to this repository."""

        return self._admission

    def enqueue(
        self,
        *,
        idempotency_key: str,
        job_kind: str,
        document_id: UUID | None = None,
        version_id: UUID | None = None,
        priority: JobPriority = JobPriority.NORMAL,
        payload_ref: dict[str, Any] | None = None,
        estimated_size_bytes: int = 0,
        estimated_cost_usd: Decimal = Decimal("0.01"),
        max_attempts: int = DEFAULT_MAX_JOB_ATTEMPTS,
    ) -> IngestionJobRecord:
        """Insert a job idempotently after admission checks.

        Args:
            idempotency_key: Stable enqueue key.
            job_kind: Internal ingestion stage identifier.
            document_id: Optional canonical document identifier.
            version_id: Optional canonical version identifier.
            priority: Queue priority band.
            payload_ref: Durable Storage/canonical pointers only.
            estimated_size_bytes: Declared byte estimate for ordering/admission.
            estimated_cost_usd: Estimated daily ingestion spend to reserve.
            max_attempts: Retry ceiling before dead-letter routing.

        Returns:
            Existing or newly inserted ingestion job row.

        Raises:
            JobAdmissionError: When admission rejects the enqueue.
        """

        existing = self._get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing
        self._admission.assert_can_enqueue_ingestion(
            estimated_size_bytes=estimated_size_bytes,
            estimated_cost_usd=estimated_cost_usd,
        )
        reservation_id = self._admission.create_ingestion_budget_reservation(
            estimated_cost_usd=estimated_cost_usd
        )
        payload = dict(payload_ref or {})
        payload["budget_reservation_id"] = str(reservation_id)
        payload["estimated_cost_usd"] = str(estimated_cost_usd)
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO app.ingestion_jobs (
                  document_id,
                  version_id,
                  job_kind,
                  priority,
                  idempotency_key,
                  payload_ref,
                  estimated_size_bytes,
                  max_attempts
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    document_id,
                    version_id,
                    job_kind,
                    priority.value,
                    idempotency_key,
                    json.dumps(payload),
                    estimated_size_bytes,
                    max_attempts,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobRepositoryError("enqueue_missing_row")
            return _row_to_ingestion_job(row)

    def _get_by_idempotency_key(
        self, idempotency_key: str
    ) -> IngestionJobRecord | None:
        """Load an ingestion job by its idempotency key.

        Args:
            idempotency_key: Unique enqueue key.

        Returns:
            The matching job, or ``None`` when the key is unused.
        """

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.ingestion_jobs
                WHERE idempotency_key = %s
                """,
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return _row_to_ingestion_job(row)

    def claim(self) -> IngestionJobRecord | None:
        """Claim one pending or expired ingestion job via ``SKIP LOCKED`` RPC.

        Returns:
            Claimed job row, or ``None`` when no eligible work exists.
        """

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.claim_ingestion_job(%s, %s)
                """,
                (self._lease_owner, self._lease_seconds),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return _row_to_ingestion_job(row)

    def heartbeat(self, job_id: UUID, lease_token: str) -> None:
        """Renew a valid ingestion lease.

        Raises:
            JobLeaseError: When the lease cannot be renewed.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.heartbeat_ingestion_job(%s, %s, %s, %s)
                """,
                (job_id, self._lease_owner, lease_token, self._lease_seconds),
            )
            row = cursor.fetchone()
            if row is None or row[0] is not True:
                raise JobLeaseError("heartbeat_rejected")

    def complete(self, job_id: UUID, lease_token: str) -> IngestionJobRecord:
        """Mark a leased job completed and release the lease.

        Raises:
            JobLeaseError: When completion is rejected.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.complete_ingestion_job(%s, %s, %s)
                """,
                (job_id, self._lease_owner, lease_token),
            )
            ok_row = cursor.fetchone()
            if ok_row is None or ok_row[0] is not True:
                raise JobLeaseError("complete_rejected")
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM app.ingestion_jobs WHERE id = %s",
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobNotFoundError(str(job_id))
            return _row_to_ingestion_job(row)

    def cancel(self, job_id: UUID, lease_token: str | None = None) -> None:
        """Cancel a pending or actively leased ingestion job."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.cancel_ingestion_job(%s, %s, %s)
                """,
                (job_id, self._lease_owner, lease_token or ""),
            )
            row = cursor.fetchone()
            if row is None or row[0] is not True:
                raise JobLeaseError("cancel_rejected")

    def fail(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        error_category: JobErrorCategory,
        last_error: str,
        move_to_dead_letter: bool = False,
    ) -> IngestionJobRecord:
        """Fail a leased job with bounded retry or terminal dead-letter routing."""

        job = self.get(job_id)
        if job.lease_token != lease_token:
            raise JobLeaseError("fail_rejected")
        if move_to_dead_letter or job.attempt_count >= job.max_attempts:
            return self._move_to_dead_letter(
                job,
                lease_token=lease_token,
                error_category=error_category,
                last_error=last_error,
            )
        delay = compute_retry_delay_seconds(job.attempt_count)
        next_attempt = datetime.now(tz=UTC) + timedelta(seconds=delay)
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET
                  status = 'pending'::app.job_status,
                  lease_owner = NULL,
                  lease_token = NULL,
                  lease_expires_at = NULL,
                  next_attempt_at = %s,
                  error_category = %s,
                  last_error = %s,
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND lease_owner = %s
                  AND lease_token = %s
                  AND status = 'processing'::app.job_status
                RETURNING *
                """,
                (
                    next_attempt,
                    error_category.value,
                    last_error[:4000],
                    job_id,
                    self._lease_owner,
                    lease_token,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobLeaseError("fail_rejected")
            return _row_to_ingestion_job(row)

    def get(self, job_id: UUID) -> IngestionJobRecord:
        """Load one ingestion job by identifier."""

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM app.ingestion_jobs WHERE id = %s",
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobNotFoundError(str(job_id))
            return _row_to_ingestion_job(row)

    def validate_active_lease(
        self, job_id: UUID, lease_token: str
    ) -> IngestionJobRecord:
        """Return the job when the lease token is currently valid.

        Raises:
            JobLeaseError: When the lease is missing, expired, or cancelled.
        """

        job = self.get(job_id)
        if (
            job.status is not JobStatus.PROCESSING
            or job.lease_token != lease_token
            or job.lease_expires_at is None
            or job.lease_expires_at < datetime.now(tz=UTC)
        ):
            raise JobLeaseError("invalid_or_expired_lease")
        return job

    def _move_to_dead_letter(
        self,
        job: IngestionJobRecord,
        *,
        lease_token: str,
        error_category: JobErrorCategory,
        last_error: str,
    ) -> IngestionJobRecord:
        """Copy an exhausted ingestion job into dead-letter storage.

        The status update is lease-conditional so a late dead-letter write
        cannot tombstone a row another worker has already claimed.

        Args:
            job: Job that has exhausted retries.
            lease_token: Lease token that must still own ``processing``.
            error_category: Classified failure category.
            last_error: Operator-visible error detail.

        Returns:
            The job record after the dead-letter insert and status update.

        Raises:
            JobLeaseError: When zero rows match the lease/status predicate.
        """

        dead_letter_key = f"dead-letter:{job.id}:{job.attempt_count}"
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET
                  status = 'dead_letter'::app.job_status,
                  lease_owner = NULL,
                  lease_token = NULL,
                  lease_expires_at = NULL,
                  error_category = %s,
                  last_error = %s,
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND lease_token = %s
                  AND status = 'processing'::app.job_status
                RETURNING *
                """,
                (error_category.value, last_error[:4000], job.id, lease_token),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobLeaseError("dead_letter_lease_rejected")
            cursor.execute(
                """
                INSERT INTO app.dead_letter_jobs (
                  source_table,
                  source_job_id,
                  priority,
                  idempotency_key,
                  payload_ref,
                  last_error,
                  error_category
                )
                VALUES (
                  'ingestion_jobs',
                  %s,
                  %s,
                  %s,
                  %s::jsonb,
                  %s,
                  %s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id
                """,
                (
                    job.id,
                    job.priority.value,
                    dead_letter_key,
                    json.dumps(
                        {
                            **job.payload_ref,
                            "source_status": job.status.value,
                            "source_attempt_count": job.attempt_count,
                        }
                    ),
                    last_error[:4000],
                    error_category.value,
                ),
            )
            reservation_raw = job.payload_ref.get("budget_reservation_id")
            if isinstance(reservation_raw, str):
                self._admission.release_ingestion_reservation(UUID(reservation_raw))
            return _row_to_ingestion_job(row)


def configurable_job_lease_token(
    config: Mapping[str, object] | object,
    fallback: str,
) -> str:
    """Return the currently claimed lease token from runnable config.

    Checkpointed graph state keeps the token from the first attempt. A later
    ``claim()`` issues a new token; canonical ledger RPCs must present that
    live token. The worker stores it on ``configurable.job_lease_token``.

    Args:
        config: LangGraph runnable config or a mapping with ``configurable``.
        fallback: Token from checkpointed state when config has none.

    Returns:
        The claimed token when present and non-empty; otherwise ``fallback``.
    """

    mapping = _as_mapping(config)
    configurable: object = mapping.get("configurable", mapping)
    if isinstance(configurable, dict):
        token = cast(dict[str, object], configurable).get("job_lease_token")
        if isinstance(token, str) and token.strip():
            return token
    return fallback


def configurable_lease_lost(config: Mapping[str, object] | object) -> bool:
    """Return whether a worker heartbeat marked the graph lease lost.

    Args:
        config: LangGraph ``RunnableConfig`` or a mapping with
            ``configurable.lease_lost`` set to a ``threading.Event``.

    Returns:
        ``True`` when the event exists and is set.
    """

    mapping = _as_mapping(config)
    configurable: object = mapping.get("configurable", mapping)
    if not isinstance(configurable, dict):
        return False
    event = cast(dict[str, object], configurable).get("lease_lost")
    is_set = getattr(event, "is_set", None)
    return bool(callable(is_set) and is_set())


def _as_mapping(config: Mapping[str, object] | object) -> Mapping[str, object]:
    """Return ``config`` as a mapping when possible.

    Args:
        config: Runnable config or other object.

    Returns:
        A string-keyed mapping, or an empty dict.
    """

    if isinstance(config, Mapping):
        return cast(Mapping[str, object], config)
    getter = getattr(config, "get", None)
    if callable(getter):
        configurable = getter("configurable", {})
        if isinstance(configurable, dict):
            return {"configurable": cast(dict[str, object], configurable)}
    return {}


def _row_to_ingestion_job(row: dict[str, Any]) -> IngestionJobRecord:
    """Convert a dict_row ingestion job record into a typed model."""

    return IngestionJobRecord(
        id=UUID(str(row["id"])),
        document_id=UUID(str(row["document_id"])) if row["document_id"] else None,
        version_id=UUID(str(row["version_id"])) if row["version_id"] else None,
        job_kind=str(row["job_kind"]),
        status=JobStatus(str(row["status"])),
        priority=JobPriority(str(row["priority"])),
        idempotency_key=str(row["idempotency_key"]),
        lease_owner=row["lease_owner"],
        lease_token=row["lease_token"],
        lease_expires_at=row["lease_expires_at"],
        heartbeat_at=row["heartbeat_at"],
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        next_attempt_at=row["next_attempt_at"],
        error_category=(
            JobErrorCategory(str(row["error_category"]))
            if row["error_category"]
            else None
        ),
        payload_ref=dict(row["payload_ref"] or {}),
        estimated_size_bytes=int(row.get("estimated_size_bytes", 0)),
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
