"""BM25 projection worker orchestration and Hybrid Ready finalization."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.ingestion.limits import DEFAULT_BM25_UPSERT_BATCH_SIZE
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer, Bm25ProjectionRow
from smart_rag_core.retrieval.bm25_verifier import Bm25ProjectionVerifier


class Bm25ProjectionService:
    """Project canonical rows to ParadeDB and finalize Hybrid Ready."""

    def __init__(
        self,
        supabase: psycopg.Connection,
        parade: psycopg.Connection,
    ) -> None:
        """Bind Supabase and ParadeDB connections for projection work."""

        self._supabase = supabase
        self._parade = parade
        self._indexer = Bm25Indexer(parade)
        self._verifier = Bm25ProjectionVerifier(supabase, parade)

    def process_upsert_job(self, *, version_id: UUID, job_id: UUID) -> bool:
        """Upsert one version batch, verify cross-system state, finalize Hybrid Ready."""

        self._indexer.ensure_projection_schema()
        rows = self._load_projection_rows(version_id)
        for offset in range(0, len(rows), DEFAULT_BM25_UPSERT_BATCH_SIZE):
            batch = tuple(rows[offset : offset + DEFAULT_BM25_UPSERT_BATCH_SIZE])
            self._indexer.upsert_batch(batch)
        self._parade.commit()

        verification = self._verifier.verify_version(version_id)
        if not verification.passed:
            return False

        with self._supabase.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT chunk_set_hash
                FROM app.document_versions
                WHERE id = %s
                """,
                (version_id,),
            )
            version_row = cursor.fetchone()
            if version_row is None:
                return False
            cursor.execute(
                """
                SELECT app.finalize_hybrid_ready(%s, %s, %s)
                """,
                (version_id, version_row["chunk_set_hash"], job_id),
            )
        return True

    def process_delete_job(self, *, version_id: UUID) -> bool:
        """Delete one version projection and verify absence."""

        deleted = self._indexer.delete_version(version_id)
        self._parade.commit()
        remaining = self._indexer.count_rows_for_version(version_id)
        return deleted >= 0 and remaining == 0

    def _load_projection_rows(self, version_id: UUID) -> list[Bm25ProjectionRow]:
        with self._supabase.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                  dc.id AS chunk_id,
                  dc.version_id,
                  dc.document_id,
                  d.title,
                  dc.section_path,
                  dc.search_normalized,
                  dc.content_hash,
                  dv.language,
                  d.visibility_generation,
                  d.visibility,
                  dv.is_current
                FROM app.document_chunks AS dc
                JOIN app.documents AS d ON d.id = dc.document_id
                JOIN app.document_versions AS dv ON dv.id = dc.version_id
                WHERE dc.version_id = %s
                  AND dc.deleted_at IS NULL
                  AND dc.is_search_representative = true
                ORDER BY dc.chunk_index ASC
                """,
                (version_id,),
            )
            rows: list[Bm25ProjectionRow] = []
            for row in cursor.fetchall():
                heading = " > ".join(row["section_path"] or [])
                rows.append(
                    Bm25ProjectionRow(
                        chunk_id=UUID(str(row["chunk_id"])),
                        version_id=UUID(str(row["version_id"])),
                        document_id=UUID(str(row["document_id"])),
                        title_search=str(row["title"]),
                        heading_search=heading or None,
                        alias_search=None,
                        body_search=str(row["search_normalized"]),
                        language=str(row["language"]) if row["language"] else None,
                        acl_scope_id=str(row["visibility"]),
                        is_current=bool(row["is_current"]),
                        visibility_generation=int(row["visibility_generation"]),
                        normalization_version="arabic_norm_v1",
                        content_hash=str(row["content_hash"])
                        if row["content_hash"]
                        else None,
                    )
                )
            return rows
