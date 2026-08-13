"""Ingestion lifecycle status queries for public APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class IngestionStatusRepository:
    """Read ingestion lifecycle and diagnostics for one document version."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one API/worker Postgres connection for status reads."""

        self._connection = connection

    def get_version_status(self, version_id: UUID) -> dict[str, Any] | None:
        """Return public lifecycle plus orthogonal diagnostics."""

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                  dv.id AS version_id,
                  dv.document_id,
                  dv.status,
                  dv.version_number,
                  dv.is_current,
                  dv.retrieval_eligible,
                  dv.chunk_set_hash,
                  dv.embedding_model,
                  dv.embedding_policy_hash,
                  dv.hybrid_verified_at,
                  dv.bm25_verified_at,
                  dv.graph_handoff_at,
                  d.title,
                  d.visibility,
                  d.graph_eligible AS document_graph_eligible,
                  d.visibility_generation,
                  (
                    SELECT count(*)
                    FROM app.document_chunks AS dc
                    WHERE dc.version_id = dv.id AND dc.deleted_at IS NULL
                  ) AS chunk_count,
                  (
                    SELECT count(*)
                    FROM app.embedding_operation_ledger AS eol
                    WHERE eol.version_id = dv.id
                  ) AS embedding_ledger_count,
                  (
                    SELECT jsonb_build_object(
                      'pending', count(*) FILTER (WHERE status = 'pending'),
                      'processing', count(*) FILTER (WHERE status = 'processing'),
                      'failed', count(*) FILTER (WHERE status = 'failed'),
                      'dead_letter', count(*) FILTER (WHERE status = 'dead_letter')
                    )
                    FROM app.bm25_index_jobs AS bj
                    WHERE bj.version_id = dv.id
                  ) AS bm25_jobs,
                  (
                    SELECT jsonb_build_object(
                      'pending', count(*) FILTER (WHERE status = 'pending'),
                      'processing', count(*) FILTER (WHERE status = 'processing')
                    )
                    FROM app.lightrag_index_jobs AS lj
                    WHERE lj.version_id = dv.id
                  ) AS graph_handoff_jobs
                FROM app.document_versions AS dv
                JOIN app.documents AS d ON d.id = dv.document_id
                WHERE dv.id = %s
                """,
                (version_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_recent_jobs(self, *, document_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent ingestion jobs with safe diagnostics."""

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                  id,
                  job_kind,
                  status,
                  priority,
                  attempt_count,
                  max_attempts,
                  error_category,
                  last_error,
                  created_at,
                  updated_at
                FROM app.ingestion_jobs
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (document_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
