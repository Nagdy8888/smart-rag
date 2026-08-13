"""Idempotent side-effect ledger backed by ``app.job_operation_ledger``."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.jobs.exceptions import JobLeaseError, JobRepositoryError


class JobOperationLedger:
    """Records graph/worker side effects with lease-validated RPC writes."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one worker-role Postgres connection.

        Args:
            connection: Active connection entitled to execute
                ``app.record_job_operation_ledger``.
        """

        self._connection = connection

    def record_completed(
        self,
        *,
        job_table: str,
        job_id: UUID,
        operation_key: str,
        lease_token: str,
        result_ref: dict[str, Any] | None = None,
    ) -> UUID:
        """Insert or return an existing ledger row for one operation key.

        Args:
            job_table: Queue table name without schema prefix.
            job_id: Owning job identifier.
            operation_key: Stable idempotency key for the side effect.
            lease_token: Active lease token authorizing the write.
            result_ref: Optional compact result metadata.

        Returns:
            Ledger row identifier.

        Raises:
            JobLeaseError: When the lease is invalid or expired.
            JobRepositoryError: When the RPC fails unexpectedly.
        """

        payload = result_ref or {}
        with self._connection.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    SELECT app.record_job_operation_ledger(
                      %s, %s, %s, %s, 'completed', %s::jsonb
                    )
                    """,
                    (
                        job_table,
                        job_id,
                        operation_key,
                        lease_token,
                        json.dumps(payload),
                    ),
                )
            except psycopg.errors.RaiseException as exc:
                message = str(exc).lower()
                if "lease" in message:
                    raise JobLeaseError("invalid_or_expired_lease") from exc
                raise JobRepositoryError("ledger_write_failed") from exc
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise JobRepositoryError("ledger_write_missing_id")
            return UUID(str(row[0]))

    def fetch_result(
        self,
        *,
        job_table: str,
        job_id: UUID,
        operation_key: str,
    ) -> dict[str, Any] | None:
        """Return a completed ledger result payload when present."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT result_ref
                FROM app.job_operation_ledger
                WHERE job_table = %s
                  AND job_id = %s
                  AND operation_key = %s
                  AND status = 'completed'
                """,
                (job_table, job_id, operation_key),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                return None
            payload = row[0]
            if isinstance(payload, dict):
                return payload
            if isinstance(payload, str):
                return json.loads(payload)
            return dict(payload)
