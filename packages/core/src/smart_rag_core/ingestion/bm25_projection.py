"""BM25 projection worker orchestration and Hybrid Ready finalization."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.ingestion.bm25_reconcile import (
    Bm25ReconcileDecision,
    decide_bm25_reconcile,
)
from smart_rag_core.ingestion.limits import DEFAULT_BM25_UPSERT_BATCH_SIZE
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer, Bm25ProjectionRow
from smart_rag_core.retrieval.bm25_verifier import Bm25ProjectionVerifier
from smart_rag_core.schema.enums import JobStatus


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
        """Upsert one version batch, verify, then finalize Hybrid Ready.

        ``app.finalize_hybrid_ready`` sets ``documents.current_version_id`` for
        graph-ineligible versions. Graph-eligible replacements stay non-current
        until Phase 5 pointer CAS.

        Args:
            version_id: Canonical document version being projected.
            job_id: Leased BM25 outbox row that must remain ``processing``.

        Returns:
            True when ParadeDB verify passed and finalize ran. False when verify
            failed; the caller must fail/retry the job and must not complete it.

        Side Effects:
            Writes ParadeDB projection rows, commits ParadeDB, and calls
            ``finalize_hybrid_ready`` on the Supabase connection (caller commits).
        """

        self._indexer.ensure_projection_schema()
        rows = self._load_projection_rows(version_id)
        for offset in range(0, len(rows), DEFAULT_BM25_UPSERT_BATCH_SIZE):
            batch = tuple(rows[offset : offset + DEFAULT_BM25_UPSERT_BATCH_SIZE])
            self._indexer.upsert_batch(batch)
        self._parade.commit()

        verification = self._verifier.verify_version(version_id)
        if not verification.passed:
            return False
        return self._finalize_hybrid_ready(version_id=version_id, job_id=job_id)

    def reconcile_upsert_job(
        self, *, version_id: UUID, job_id: UUID
    ) -> Bm25ReconcileDecision:
        """Repair a leased processing upsert without writing ParadeDB rows.

        Args:
            version_id: Canonical version on the outbox row.
            job_id: Leased BM25 job that must remain ``processing`` until the
                worker completes or fails it.

        Returns:
            Decision. ``complete`` / ``finalize_then_complete`` require verify.
            ``fail`` means the worker must fail/retry/dead-letter.

        Side Effects:
            May call ``finalize_hybrid_ready`` only when verify passed and the
            version is still pre-hybrid. Never marks the outbox ``completed``.
        """

        verification = self._verifier.verify_version(version_id)
        if not verification.passed:
            return decide_bm25_reconcile(
                job_status=JobStatus.PROCESSING.value,
                job_operation="upsert",
                verify_passed=False,
                version_status=self._version_status(version_id),
            )
        version_status = self._version_status(version_id)
        decision = decide_bm25_reconcile(
            job_status=JobStatus.PROCESSING.value,
            job_operation="upsert",
            verify_passed=True,
            version_status=version_status,
        )
        if decision.action == "finalize_then_complete":
            finalized = self._finalize_hybrid_ready(
                version_id=version_id, job_id=job_id
            )
            if not finalized:
                return Bm25ReconcileDecision(
                    action="fail",
                    reason="finalize_hybrid_ready_failed",
                )
            return Bm25ReconcileDecision(
                action="complete",
                reason=decision.reason,
            )
        return decision

    def reconcile_delete_job(self, *, version_id: UUID) -> Bm25ReconcileDecision:
        """Repair a leased processing delete without issuing a new delete.

        Args:
            version_id: Canonical version whose ParadeDB rows must be absent.

        Returns:
            ``complete`` when zero ParadeDB rows remain; ``fail`` otherwise.

        Side Effects:
            Read-only ParadeDB count. Does not mark the outbox completed.
        """

        remaining = self._indexer.count_rows_for_version(version_id)
        return decide_bm25_reconcile(
            job_status=JobStatus.PROCESSING.value,
            job_operation="delete",
            verify_passed=remaining == 0,
            version_status=None,
        )

    def process_delete_job(self, *, version_id: UUID) -> bool:
        """Delete one version projection and verify absence."""

        deleted = self._indexer.delete_version(version_id)
        self._parade.commit()
        remaining = self._indexer.count_rows_for_version(version_id)
        return deleted >= 0 and remaining == 0

    def _finalize_hybrid_ready(self, *, version_id: UUID, job_id: UUID) -> bool:
        """Call ``finalize_hybrid_ready`` after a successful verify.

        Args:
            version_id: Canonical version.
            job_id: Processing BM25 upsert job.

        Returns:
            False when the version row is missing.

        Side Effects:
            Worker-role RPC. Caller commits Supabase.
        """

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

    def _version_status(self, version_id: UUID) -> str | None:
        """Return the public document-version status.

        Args:
            version_id: Canonical version.

        Returns:
            Status enum string, or ``None`` when the row is missing.
        """

        with self._supabase.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM app.document_versions WHERE id = %s",
                (version_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return str(row[0])

    def _load_projection_rows(self, version_id: UUID) -> list[Bm25ProjectionRow]:
        """Load canonical representative chunks as ParadeDB projection rows.

        Args:
            version_id: Canonical version.

        Returns:
            Ordered projection rows for upsert.
        """

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
