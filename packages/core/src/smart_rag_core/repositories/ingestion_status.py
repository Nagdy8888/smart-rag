"""Ingestion lifecycle status queries for public APIs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class IngestionStatusRepository:
    """Read ingestion lifecycle and diagnostics for one document version."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one API/worker Postgres connection for status reads.

        Args:
            connection: Open connection; callers set ``app_api`` or ``app_worker``.
        """

        self._connection = connection

    def get_version_status(self, version_id: UUID) -> dict[str, Any] | None:
        """Return public lifecycle plus nested orthogonal diagnostics.

        Nested objects cover scan evidence, review/governance, OCR pages,
        chunk/table counts, embedding ledger, BM25 index version/lag/retry/
        dead-letter, queue age, and graph-handoff counts. They do not add
        public lifecycle enums.

        Args:
            version_id: Canonical document version identifier.

        Returns:
            Row dict matching ``IngestionStatusResponse`` field names, or
            ``None`` when the version is missing.
        """

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
                  ) AS graph_handoff_jobs,
                  (
                    SELECT jsonb_build_object(
                      'result', se.result,
                      'evidence_id', se.id,
                      'scanned_at', se.scanned_at,
                      'age_seconds', extract(
                        epoch FROM (timezone('utc', now()) - se.scanned_at)
                      ),
                      'engine_version', se.scan_engine_version,
                      'signature_version', se.signature_version,
                      'object_hash', se.object_hash
                    )
                    FROM app.document_scan_events AS se
                    WHERE se.version_id = dv.id
                    ORDER BY se.scanned_at DESC
                    LIMIT 1
                  ) AS scan,
                  (
                    SELECT jsonb_build_object(
                      'declared_category', ds.declared_category,
                      'source_type', ds.source_type,
                      'approval_status', (
                        SELECT sar.status
                        FROM app.source_approval_requests AS sar
                        WHERE sar.source_id = ds.id
                        ORDER BY sar.updated_at DESC
                        LIMIT 1
                      ),
                      'attestation_policy_version', (
                        SELECT j.payload_ref ->> 'attestation_policy_version'
                        FROM app.ingestion_jobs AS j
                        WHERE j.version_id = dv.id
                        ORDER BY j.created_at
                        LIMIT 1
                      )
                    )
                    FROM app.document_sources AS ds
                    WHERE ds.version_id = dv.id
                    ORDER BY ds.created_at
                    LIMIT 1
                  ) AS review,
                  jsonb_build_object(
                    'page_count', coalesce((
                      SELECT count(DISTINCT dc.page_number)
                      FROM app.document_chunks AS dc
                      WHERE dc.version_id = dv.id
                        AND dc.deleted_at IS NULL
                        AND dc.page_number IS NOT NULL
                    ), 0),
                    'ocr_pages', coalesce((
                      SELECT count(DISTINCT dc.page_number)
                      FROM app.document_chunks AS dc
                      WHERE dc.version_id = dv.id
                        AND dc.deleted_at IS NULL
                        AND dc.page_number IS NOT NULL
                        AND coalesce((dc.provenance ->> 'ocr')::boolean, false)
                    ), 0)
                  ) AS ocr,
                  jsonb_build_object(
                    'chunk_count', (
                      SELECT count(*)
                      FROM app.document_chunks AS dc
                      WHERE dc.version_id = dv.id AND dc.deleted_at IS NULL
                    ),
                    'table_count', (
                      SELECT count(*)
                      FROM app.document_tables AS dt
                      WHERE dt.version_id = dv.id
                    )
                  ) AS chunks_tables,
                  jsonb_build_object(
                    'ledger_count', (
                      SELECT count(*)
                      FROM app.embedding_operation_ledger AS eol
                      WHERE eol.version_id = dv.id
                    ),
                    'completed_count', (
                      SELECT count(*)
                      FROM app.embedding_operation_ledger AS eol
                      WHERE eol.version_id = dv.id AND eol.status = 'completed'
                    ),
                    'failed_count', (
                      SELECT count(*)
                      FROM app.embedding_operation_ledger AS eol
                      WHERE eol.version_id = dv.id AND eol.status = 'failed'
                    ),
                    'model', dv.embedding_model,
                    'policy_hash', dv.embedding_policy_hash
                  ) AS embedding,
                  jsonb_build_object(
                    'active_index_version', (
                      SELECT biv.version_number
                      FROM app.bm25_index_versions AS biv
                      WHERE biv.is_active = true
                      ORDER BY biv.version_number DESC
                      LIMIT 1
                    ),
                    'index_schema_version', (
                      SELECT biv.index_schema_version
                      FROM app.bm25_index_versions AS biv
                      WHERE biv.is_active = true
                      ORDER BY biv.version_number DESC
                      LIMIT 1
                    ),
                    'lag_seconds', CASE
                      WHEN dv.hybrid_verified_at IS NOT NULL
                        AND dv.bm25_verified_at IS NULL THEN
                        extract(
                          epoch FROM (
                            timezone('utc', now()) - dv.hybrid_verified_at
                          )
                        )
                      WHEN EXISTS (
                        SELECT 1
                        FROM app.bm25_index_jobs AS bj
                        WHERE bj.version_id = dv.id
                          AND bj.status IN ('pending', 'processing')
                      ) THEN
                        extract(
                          epoch FROM (
                            timezone('utc', now()) - (
                              SELECT min(bj.created_at)
                              FROM app.bm25_index_jobs AS bj
                              WHERE bj.version_id = dv.id
                                AND bj.status IN ('pending', 'processing')
                            )
                          )
                        )
                      ELSE NULL
                    END,
                    'pending', (
                      SELECT count(*)
                      FROM app.bm25_index_jobs AS bj
                      WHERE bj.version_id = dv.id AND bj.status = 'pending'
                    ),
                    'processing', (
                      SELECT count(*)
                      FROM app.bm25_index_jobs AS bj
                      WHERE bj.version_id = dv.id AND bj.status = 'processing'
                    ),
                    'failed', (
                      SELECT count(*)
                      FROM app.bm25_index_jobs AS bj
                      WHERE bj.version_id = dv.id AND bj.status = 'failed'
                    ),
                    'dead_letter', (
                      SELECT count(*)
                      FROM app.bm25_index_jobs AS bj
                      WHERE bj.version_id = dv.id AND bj.status = 'dead_letter'
                    ),
                    'retry_attempts', (
                      SELECT coalesce(sum(bj.attempt_count), 0)
                      FROM app.bm25_index_jobs AS bj
                      WHERE bj.version_id = dv.id
                    ),
                    'verified_at', dv.bm25_verified_at
                  ) AS bm25,
                  (
                    SELECT jsonb_build_object(
                      'oldest_pending_job_age_seconds', extract(
                        epoch FROM (timezone('utc', now()) - j.created_at)
                      ),
                      'oldest_pending_job_kind', j.job_kind
                    )
                    FROM app.ingestion_jobs AS j
                    WHERE j.version_id = dv.id AND j.status = 'pending'
                    ORDER BY j.created_at
                    LIMIT 1
                  ) AS queue_age,
                  (
                    SELECT jsonb_build_object(
                      'pending', count(*) FILTER (WHERE status = 'pending'),
                      'processing', count(*) FILTER (WHERE status = 'processing'),
                      'completed', count(*) FILTER (WHERE status = 'completed'),
                      'failed', count(*) FILTER (WHERE status = 'failed'),
                      'dead_letter', count(*) FILTER (WHERE status = 'dead_letter')
                    )
                    FROM app.lightrag_index_jobs AS lj
                    WHERE lj.version_id = dv.id
                  ) AS graph_handoff
                FROM app.document_versions AS dv
                JOIN app.documents AS d ON d.id = dv.document_id
                WHERE dv.id = %s
                """,
                (version_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_recent_jobs(self, *, document_id: UUID, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent ingestion jobs with safe diagnostics.

        Args:
            document_id: Canonical document identifier.
            limit: Maximum rows to return.

        Returns:
            Job summary dicts newest-first.
        """

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
