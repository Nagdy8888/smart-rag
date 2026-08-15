"""BM25 projection job repository with lease semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.jobs.backoff import compute_retry_delay_seconds
from smart_rag_core.jobs.exceptions import (
    JobLeaseError,
    JobNotFoundError,
)
from smart_rag_core.jobs.limits import DEFAULT_MAX_JOB_ATTEMPTS
from smart_rag_core.schema.enums import JobErrorCategory, JobStatus


class Bm25IndexJobRepository:
    """Worker-facing BM25 outbox persistence."""

    def __init__(
        self,
        connection: psycopg.Connection,
        *,
        lease_owner: str,
        lease_seconds: int,
    ) -> None:
        """Bind worker connection and lease parameters for claim RPCs."""

        self._connection = connection
        self._lease_owner = lease_owner
        self._lease_seconds = lease_seconds

    def claim(self) -> dict[str, Any] | None:
        """Claim one eligible BM25 projection job."""

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.claim_bm25_index_job(%s, %s)
                """,
                (self._lease_owner, self._lease_seconds),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def heartbeat(self, job_id: UUID, lease_token: str) -> None:
        """Renew an active BM25 job lease."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.bm25_index_jobs
                SET
                  heartbeat_at = timezone('utc', now()),
                  lease_expires_at = timezone('utc', now()) + make_interval(secs => %s),
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND lease_token = %s
                  AND lease_owner = %s
                  AND status = 'processing'::app.job_status
                RETURNING id
                """,
                (self._lease_seconds, job_id, lease_token, self._lease_owner),
            )
            if cursor.fetchone() is None:
                raise JobLeaseError("heartbeat_rejected")

    def complete(self, job_id: UUID, lease_token: str) -> dict[str, Any]:
        """Mark one BM25 job completed."""

        return self._transition(job_id, lease_token, status=JobStatus.COMPLETED)

    def fail(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        error_category: JobErrorCategory,
        last_error: str,
    ) -> dict[str, Any]:
        """Mark one BM25 job failed with retry scheduling."""

        job = self._get_job(job_id)
        attempt = int(job.get("attempt_count", 0))
        max_attempts = int(job.get("max_attempts", DEFAULT_MAX_JOB_ATTEMPTS))
        next_status = (
            JobStatus.DEAD_LETTER if attempt >= max_attempts else JobStatus.PENDING
        )
        delay = compute_retry_delay_seconds(attempt)
        next_attempt = datetime.now(tz=UTC) + timedelta(seconds=delay)
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE app.bm25_index_jobs
                SET
                  status = %s,
                  error_category = %s,
                  last_error = %s,
                  lease_owner = NULL,
                  lease_token = NULL,
                  lease_expires_at = NULL,
                  next_attempt_at = %s,
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND lease_token = %s
                RETURNING *
                """,
                (
                    next_status.value,
                    error_category.value,
                    last_error[:4000],
                    next_attempt if next_status == JobStatus.PENDING else None,
                    job_id,
                    lease_token,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobLeaseError("invalid_or_expired_lease")
            return dict(row)

    def _transition(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        status: JobStatus,
    ) -> dict[str, Any]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE app.bm25_index_jobs
                SET
                  status = %s,
                  lease_owner = NULL,
                  lease_token = NULL,
                  lease_expires_at = NULL,
                  next_attempt_at = NULL,
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND lease_token = %s
                RETURNING *
                """,
                (status.value, job_id, lease_token),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobLeaseError("invalid_or_expired_lease")
            return dict(row)

    def _get_job(self, job_id: UUID) -> dict[str, Any]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM app.bm25_index_jobs WHERE id = %s",
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise JobNotFoundError(str(job_id))
            return dict(row)
