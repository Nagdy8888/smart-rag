"""Hybrid Ready persist and BM25 projection for the candidate seed.

This driver reuses the Phase 4 parse→chunk→embed→canonical→BM25 path. It
does not SQL-stamp ``hybrid_ready``. Restricted documents stay graph-ineligible.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.ingestion.canonical.repository import CanonicalRepository
from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.embeddings.service import (
    EmbeddingBatchInput,
    EmbeddingService,
)
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.parser.types import ParseResult
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    ExternalProcessingDecisionInput,
)
from smart_rag_core.settings import SharedSettings

_ALLOWED_VISIBILITY = frozenset({"company_visible", "restricted"})


@dataclass(frozen=True, slots=True)
class CandidateHybridResult:
    """Outcome of one candidate Hybrid Ready drive.

    Attributes:
        document_id: Canonical document.
        version_id: Canonical version.
        bm25_job_id: BM25 outbox job.
        status: Public document status after finalize.
        hybrid_ready: True when BM25 verify passed and status is ready or
            graph-ineligible/pending.
        chunk_count: Persisted canonical chunks.
        graph_eligible: Whether the document was marked graph-eligible.
    """

    document_id: UUID
    version_id: UUID
    bm25_job_id: UUID | None
    status: str
    hybrid_ready: bool
    chunk_count: int
    graph_eligible: bool


def parse_local_bytes(payload: bytes, *, filename: str, format_key: str) -> ParseResult:
    """Parse fixture bytes through the in-process adapter.

    Args:
        payload: Exact object bytes.
        filename: Name used for the temp file suffix.
        format_key: Adapter key such as ``markdown``.

    Returns:
        Closed parse result.
    """

    digest = hashlib.sha256(payload).hexdigest()
    with tempfile.TemporaryDirectory(prefix="phase09-hybrid-") as temp_dir:
        path = Path(temp_dir) / filename
        path.write_bytes(payload)
        return parse_file(path, digest, format_key)


def persist_parse_to_bm25_outbox(
    supabase: psycopg.Connection,
    *,
    parse_result: ParseResult,
    title: str,
    filename: str,
    settings: SharedSettings | None = None,
    visibility: str = "company_visible",
    graph_eligible: bool = False,
) -> tuple[UUID, UUID, UUID]:
    """Create a version, embed through the shared gateway, and enqueue BM25.

    Args:
        supabase: Open worker-capable connection (caller sets role).
        parse_result: Closed parser output.
        title: Document title.
        filename: Original filename for search-term extraction.
        settings: Optional settings. When omitted, mock-model mode is forced.
        visibility: ``company_visible`` or ``restricted``.
        graph_eligible: Company-visible graph indexing eligibility.

    Returns:
        ``(document_id, version_id, bm25_job_id)``.

    Raises:
        ValueError: If ``visibility`` is not allow-listed.
        ValueError: If restricted visibility is marked graph-eligible.

    Side Effects:
        Inserts document, version, chunks, embedding ledger, and BM25 outbox.
    """

    if visibility not in _ALLOWED_VISIBILITY:
        raise ValueError("visibility must be company_visible or restricted")
    if visibility == "restricted" and graph_eligible:
        raise ValueError("restricted documents cannot be graph_eligible")
    document_id = uuid4()
    version_id = uuid4()
    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, graph_eligible)
            VALUES (%s, %s, %s::app.document_visibility, %s)
            """,
            (document_id, title, visibility, graph_eligible),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status, graph_eligible
            )
            VALUES (%s, %s, 1, 'parsing', %s)
            """,
            (version_id, document_id, graph_eligible),
        )
    supabase.execute("SET ROLE app_worker")
    chunking = chunk_parse_result(
        parse_result,
        document_id=document_id,
        version_id=version_id,
    )
    gateway = create_embedding_gateway(
        settings if settings is not None else SharedSettings(mock_model_mode=True)
    )
    embedding_service = EmbeddingService(supabase, gateway=gateway)
    embedding = embedding_service.embed_version(
        EmbeddingBatchInput(
            version_id=version_id,
            document_title=title,
            chunks=chunking.chunks,
            chunking_config_hash=chunking.config_hash,
            operation_key=f"phase09-hybrid:{version_id}",
            governance=ExternalProcessingDecisionInput(
                attestation_present=True,
                category=CategoryDisposition.ALLOWED,
                review_approved=True,
                scan_evidence_current=True,
                provider_settings_verified=True,
                policy_version_matches=True,
                content_class=ContentClass.SYNTHETIC,
            ),
            estimated_cost_usd=Decimal("0.01"),
        )
    )
    repository = CanonicalRepository(supabase)
    bm25_job_id = repository.persist_version_indexing(
        version_id=version_id,
        document_id=document_id,
        document_title=title,
        filename=filename,
        chunking=chunking,
        embedding=embedding,
        embedded=embedding.embedded,
        table_artifacts=chunking.table_artifacts,
        is_current=False,
    )
    supabase.commit()
    return document_id, version_id, bm25_job_id


def mark_bm25_job_processing(supabase: psycopg.Connection, job_id: UUID) -> None:
    """Force a pending BM25 upsert into ``processing`` for Hybrid Ready finalize.

    Args:
        supabase: Worker-role connection.
        job_id: BM25 outbox job identifier.

    Side Effects:
        Updates ``app.bm25_index_jobs.status`` to ``processing``.
    """

    with supabase.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.bm25_index_jobs
            SET status = 'processing'::app.job_status,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (job_id,),
        )


def drive_hybrid_ready(
    *,
    supabase_url: str,
    parade_url: str,
    parse_result: ParseResult,
    title: str,
    filename: str,
    settings: SharedSettings | None = None,
    visibility: str = "company_visible",
    graph_eligible: bool = False,
) -> CandidateHybridResult:
    """Persist canonical rows, project BM25, and finalize Hybrid Ready.

    Args:
        supabase_url: Local Supabase Postgres URL.
        parade_url: ParadeDB writer URL reachable from this process.
        parse_result: Closed parser output.
        title: Document title.
        filename: Original filename.
        settings: Optional settings for the embedding gateway.
        visibility: Document visibility used at insert time.
        graph_eligible: Company-visible graph eligibility.

    Returns:
        Drive outcome including public version status.
    """

    with (
        psycopg.connect(supabase_url) as supabase,
        psycopg.connect(parade_url, connect_timeout=8) as parade,
    ):
        document_id, version_id, bm25_job_id = persist_parse_to_bm25_outbox(
            supabase,
            parse_result=parse_result,
            title=title,
            filename=filename,
            settings=settings,
            visibility=visibility,
            graph_eligible=graph_eligible,
        )
        supabase.execute("SET ROLE app_worker")
        mark_bm25_job_processing(supabase, bm25_job_id)
        supabase.commit()
        parade.execute("SET ROLE paradedb_writer")
        service = Bm25ProjectionService(supabase, parade)
        passed = service.process_upsert_job(
            version_id=version_id,
            job_id=bm25_job_id,
        )
        if passed:
            supabase.commit()
            parade.commit()
        else:
            supabase.rollback()
            parade.rollback()
        supabase.execute("RESET ROLE")
        with supabase.cursor() as cursor:
            cursor.execute(
                """
                SELECT status
                FROM app.document_versions
                WHERE id = %s
                """,
                (version_id,),
            )
            status_row = cursor.fetchone()
            cursor.execute(
                """
                SELECT count(*)
                FROM app.document_chunks
                WHERE version_id = %s
                """,
                (version_id,),
            )
            count_row = cursor.fetchone()
        status = str(status_row[0]) if status_row is not None else "missing"
        chunk_count = int(count_row[0]) if count_row is not None else 0
        ready_states = {"hybrid_ready", "graph_ineligible", "graph_pending"}
        return CandidateHybridResult(
            document_id=document_id,
            version_id=version_id,
            bm25_job_id=bm25_job_id,
            status=status,
            hybrid_ready=passed and status in ready_states,
            chunk_count=chunk_count,
            graph_eligible=graph_eligible,
        )
