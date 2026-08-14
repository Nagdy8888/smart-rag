"""Dead-letter replay helpers preserving original failure evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.jobs.exceptions import (
    JobNotFoundError,
    JobRepositoryError,
    JobRetryNotAllowedError,
)
from smart_rag_core.schema.enums import JobErrorCategory, JobPriority, JobStatus
from smart_rag_core.schema.tables import IngestionJobRecord


class DeadLetterService:
    """Requeue traceable replay attempts from ``app.dead_letter_jobs``."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one worker-role or API-role Postgres connection.

        Args:
            connection: Active connection entitled to execute
                ``app.retry_ingestion_job`` and, for direct DL-id replay,
                ``SELECT`` on ``app.dead_letter_jobs``.
        """

        self._connection = connection

    def retry_ingestion(self, job_id: UUID) -> IngestionRetryResult:
        """Retry one ingestion job through the SECURITY DEFINER RPC.

        Dead-letter jobs create a **new** pending row with a fresh
        ``idempotency_key``; the original dead-letter evidence is retained.
        Backoff-pending and explicit ``failed`` rows only clear
        ``next_attempt_at`` (and restore ``pending`` for ``failed``).
        ``last_error`` and ``attempt_count`` are never wiped.

        Args:
            job_id: Source ingestion job identifier (the dead-letter or
                backoff/failed row, not the replay child).

        Returns:
            Replay or requeue result including the job that should run next.

        Raises:
            JobNotFoundError: When the source job or DL row is missing.
            JobRetryNotAllowedError: When the job is not retryable.
            JobRepositoryError: When the RPC fails unexpectedly.
        """

        with self._connection.cursor(row_factory=dict_row) as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM app.retry_ingestion_job(%s)",
                    (job_id,),
                )
            except psycopg.errors.RaiseException as exc:
                message = str(exc)
                if "ingestion_job_not_found" in message or "dead_letter_row_not_found" in message:
                    raise JobNotFoundError(str(job_id)) from exc
                if "retry_not_allowed" in message:
                    raise JobRetryNotAllowedError("retry_not_allowed") from exc
                raise JobRepositoryError("retry_ingestion_failed") from exc
            row = cursor.fetchone()
            if row is None:
                raise JobRepositoryError("retry_ingestion_missing_row")
            detail = str(row["detail"])
            original_job_id = UUID(str(row["original_job_id"]))
            job = _row_to_ingestion_job(row)
            return IngestionRetryResult(
                job=job,
                detail=detail,
                original_job_id=original_job_id,
            )

    def replay_ingestion(
        self,
        dead_letter_id: UUID,
        *,
        replay_suffix: str | None = None,
    ) -> IngestionJobRecord:
        """Create a new ingestion attempt linked to dead-letter evidence.

        Args:
            dead_letter_id: Existing dead-letter row identifier.
            replay_suffix: Optional suffix; defaults to a UTC timestamp token.

        Returns:
            Newly inserted ingestion job row in ``pending`` status.

        Raises:
            JobNotFoundError: When the dead-letter row is absent.
            JobRepositoryError: When replay cannot derive source metadata.
        """

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.dead_letter_jobs
                WHERE id = %s
                """,
                (dead_letter_id,),
            )
            dead_letter = cursor.fetchone()
            if dead_letter is None:
                raise JobNotFoundError(str(dead_letter_id))
            if dead_letter["source_table"] != "ingestion_jobs":
                raise JobRepositoryError("unsupported_dead_letter_source")
            source_job_id = UUID(str(dead_letter["source_job_id"]))
            cursor.execute(
                "SELECT * FROM app.ingestion_jobs WHERE id = %s",
                (source_job_id,),
            )
            source_job = cursor.fetchone()
            if source_job is None:
                raise JobRepositoryError("missing_source_job")
            suffix = replay_suffix or datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
            replay_key = f"replay:{source_job['idempotency_key']}:{suffix}"
            payload: dict[str, Any] = dict(source_job["payload_ref"] or {})
            payload["replay_of_dead_letter_id"] = str(dead_letter_id)
            payload["replay_of_source_job_id"] = str(source_job_id)
            payload["original_last_error"] = dead_letter["last_error"]
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
                  max_attempts,
                  status
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, 'pending'::app.job_status)
                RETURNING *
                """,
                (
                    source_job["document_id"],
                    source_job["version_id"],
                    source_job["job_kind"],
                    source_job["priority"],
                    replay_key,
                    json.dumps(payload),
                    source_job.get("estimated_size_bytes", 0),
                    source_job["max_attempts"],
                ),
            )
            replay_row = cursor.fetchone()
            if replay_row is None:
                raise JobRepositoryError("replay_insert_failed")
            cursor.execute(
                """
                UPDATE app.dead_letter_jobs
                SET
                  payload_ref = payload_ref || %s::jsonb,
                  updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (
                    json.dumps(
                        {
                            "last_replay_job_id": str(replay_row["id"]),
                            "last_replay_at": datetime.now(tz=UTC).isoformat(),
                        }
                    ),
                    dead_letter_id,
                ),
            )
            return _row_to_ingestion_job(replay_row)


@dataclass(frozen=True, slots=True)
class IngestionRetryResult:
    """Outcome of ``app.retry_ingestion_job``.

    Attributes:
        job: Job row that should be processed next (new row for DL replay).
        detail: Stable machine-readable result code.
        original_job_id: Source job identifier passed to retry.
    """

    job: IngestionJobRecord
    detail: str
    original_job_id: UUID


def _row_to_ingestion_job(row: dict[str, Any]) -> IngestionJobRecord:
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
