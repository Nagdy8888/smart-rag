"""LightRAG index job repository with graph-handoff pause awareness."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.jobs.exceptions import JobRepositoryError
from smart_rag_core.jobs.limits import GRAPH_HANDOFF_PAUSE_PENDING_INDEX
from smart_rag_core.schema.enums import LightragJobOperation


class LightragIndexJobRepository:
    """Claim LightRAG handoff jobs through the SQL pause-aware RPC."""

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

    def claim(self) -> dict[str, object] | None:
        """Claim one eligible LightRAG job row."""

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.claim_lightrag_index_job(%s, %s)
                """,
                (self._lease_owner, self._lease_seconds),
            )
            return cursor.fetchone()

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
