"""LightRAG index job repository with graph-handoff pause awareness."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
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
from smart_rag_core.jobs.limits import (
    DEFAULT_MAX_JOB_ATTEMPTS,
    GRAPH_HANDOFF_PAUSE_PENDING_INDEX,
)
from smart_rag_core.schema.enums import (
    JobErrorCategory,
    JobStatus,
    LightragJobOperation,
)


class LightragIndexJobRepository:
    """Claim LightRAG handoff jobs through the SQL pause-aware RPC."""

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> None:
        """Bind worker connection and lease parameters for claim RPCs.

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

    def pending_index_handoffs(self) -> int:
        """Return pending ``index`` operations used by the graph-handoff pause."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.lightrag_index_jobs
                WHERE status = 'pending'::app.job_status
                  AND operation = 'index'::app.lightrag_job_operation
                """
            )
            row = cursor.fetchone()
            if row is None:
                return 0
            return int(row[0])

    def graph_handoff_paused(self) -> bool:
        """Return whether new ``index`` claims are paused."""

        return self.pending_index_handoffs() > GRAPH_HANDOFF_PAUSE_PENDING_INDEX

    def claim(self) -> dict[str, Any] | None:
        """Claim one eligible LightRAG job row."""

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.claim_lightrag_index_job(%s, %s)
                """,
                (self._lease_owner, self._lease_seconds),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def enqueue_index_handoff(
        self,
        *,
        idempotency_key: str,
        document_id: UUID,
        version_id: UUID,
    ) -> UUID:
        """Insert one pending graph index handoff job."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.lightrag_index_jobs (
                  document_id,
                  version_id,
                  operation,
                  idempotency_key
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id
                """,
                (
                    document_id,
                    version_id,
                    LightragJobOperation.INDEX.value,
                    idempotency_key,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    SELECT id
                    FROM app.lightrag_index_jobs
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                )
                row = cursor.fetchone()
            if row is None:
                raise JobRepositoryError("lightrag_enqueue_missing_row")
            return UUID(str(row[0]))

    def get(self, job_id: UUID) -> dict[str, Any]:
        """Load one LightRAG job by identifier.

        Args:
            job_id: Job primary key.

        Returns:
            Job row mapping.

        Raises:
            JobNotFoundError: If the row is missing.
        """

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM app.lightrag_index_jobs WHERE id = %s",
                (job_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise JobNotFoundError(str(job_id))
        return dict(row)

    def heartbeat(self, job_id: UUID, lease_token: str) -> None:
        """Renew a valid LightRAG job lease.

        Args:
            job_id: Claimed job identifier.
            lease_token: Lease token from claim.

        Raises:
            JobLeaseError: When the lease cannot be renewed.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.heartbeat_lightrag_index_job(%s, %s, %s, %s)
                """,
                (job_id, self._lease_owner, lease_token, self._lease_seconds),
            )
            row = cursor.fetchone()
        if row is None or row[0] is not True:
            raise JobLeaseError("heartbeat_rejected")

    def complete(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark a leased LightRAG job completed.

        Args:
            job_id: Claimed job identifier.
            lease_token: Lease token from claim.
            result: Optional JSON merged into ``payload_ref``. Must not claim
                mapping-verified completion.

        Returns:
            Completed job row.

        Raises:
            JobLeaseError: When completion is rejected.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.complete_lightrag_index_job(%s, %s, %s, %s::jsonb)
                """,
                (
                    job_id,
                    self._lease_owner,
                    lease_token,
                    json.dumps(result or {}),
                ),
            )
            ok_row = cursor.fetchone()
        if ok_row is None or ok_row[0] is not True:
            raise JobLeaseError("complete_rejected")
        return self.get(job_id)

    def validate_active_lease(self, job_id: UUID, lease_token: str) -> dict[str, Any]:
        """Return the job when the lease token is currently valid.

        Args:
            job_id: Claimed job identifier.
            lease_token: Lease token from claim.

        Returns:
            Job row mapping.

        Raises:
            JobLeaseError: When the lease is missing, expired, or cancelled.
        """

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.validate_active_lightrag_lease(%s, %s, %s)
                """,
                (job_id, self._lease_owner, lease_token),
            )
            row = cursor.fetchone()
        if row is None or row[0] is not True:
            raise JobLeaseError("invalid_or_expired_lease")
        return self.get(job_id)

    def fail(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        error_category: JobErrorCategory,
        last_error: str,
        move_to_dead_letter: bool = False,
    ) -> dict[str, Any]:
        """Fail a leased LightRAG job with bounded retry or dead-letter.

        Args:
            job_id: Claimed job identifier.
            lease_token: Lease token from claim.
            error_category: Retry classification.
            last_error: Bounded error text.
            move_to_dead_letter: Force terminal dead-letter routing.

        Returns:
            Updated job row.

        Raises:
            JobLeaseError: When the fail RPC is rejected.
        """

        job = self.get(job_id)
        attempt = int(job.get("attempt_count", 0))
        max_attempts = int(job.get("max_attempts", DEFAULT_MAX_JOB_ATTEMPTS))
        terminal = move_to_dead_letter or attempt >= max_attempts
        if terminal:
            self._insert_dead_letter(
                job,
                error_category=error_category,
                last_error=last_error,
            )
            next_status = JobStatus.DEAD_LETTER
            next_attempt = None
        else:
            next_status = JobStatus.PENDING
            delay = compute_retry_delay_seconds(attempt)
            next_attempt = datetime.now(tz=UTC) + timedelta(seconds=delay)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.fail_lightrag_index_job(
                  %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    job_id,
                    self._lease_owner,
                    lease_token,
                    error_category.value,
                    last_error[:4000],
                    next_status.value,
                    next_attempt,
                ),
            )
            ok_row = cursor.fetchone()
        if ok_row is None or ok_row[0] is not True:
            raise JobLeaseError("fail_rejected")
        return self.get(job_id)

    def _insert_dead_letter(
        self,
        job: dict[str, Any],
        *,
        error_category: JobErrorCategory,
        last_error: str,
    ) -> None:
        """Insert one LightRAG job into the shared dead-letter table.

        Args:
            job: Source LightRAG job row, including payload and attempt count.
            error_category: Classified failure category.
            last_error: Operator-visible error detail.
        """

        dead_letter_key = f"dead-letter:{job['id']}:{job.get('attempt_count', 0)}"
        payload = dict(job.get("payload_ref") or {})
        payload["source_status"] = str(job.get("status"))
        payload["source_attempt_count"] = int(job.get("attempt_count", 0))
        with self._connection.cursor() as cursor:
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
                  'lightrag_index_jobs',
                  %s,
                  %s,
                  %s,
                  %s::jsonb,
                  %s,
                  %s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                (
                    job["id"],
                    str(job.get("priority", "normal")),
                    dead_letter_key,
                    json.dumps(payload),
                    last_error[:4000],
                    error_category.value,
                ),
            )
