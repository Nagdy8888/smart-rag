"""Drive a synthetic parse→chunk→mock-embed→canonical→BM25 Hybrid Ready path.

Packet 8 uses this helper from contract tests and the throughput script. Real
OpenAI embeddings are never called.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
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

from tests.contract.integration_support import ensure_paradedb_bm25_index


@dataclass(frozen=True, slots=True)
class HybridReadyDriveResult:
    """Outcome of one synthetic Hybrid Ready drive."""

    document_id: UUID
    version_id: UUID
    bm25_job_id: UUID | None
    hybrid_ready: bool
    status: str
    detail: str


def persist_parse_to_bm25_outbox(
    supabase: psycopg.Connection,
    *,
    parse_result: ParseResult,
    title: str,
    filename: str,
) -> tuple[UUID, UUID, UUID]:
    """Create a version, embed with the mock gateway, and enqueue BM25.

    Args:
        supabase: Open worker-capable connection (caller sets role).
        parse_result: Closed parser output for one file or merged website.
        title: Document title.
        filename: Original filename for search-term extraction.

    Returns:
        ``(document_id, version_id, bm25_job_id)``.

    Side Effects:
        Inserts document, version, chunks, embedding ledger, and BM25 outbox.
    """

    document_id = uuid4()
    version_id = uuid4()
    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app.documents (id, title) VALUES (%s, %s)",
            (document_id, title),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status
            )
            VALUES (%s, %s, 1, 'parsing')
            """,
            (version_id, document_id),
        )
    supabase.execute("SET ROLE app_worker")
    chunking = chunk_parse_result(
        parse_result,
        document_id=document_id,
        version_id=version_id,
    )
    gateway = EmbeddingGateway(MockEmbeddingAdapter(fixture_id="phase3-packet8"))
    embedding_service = EmbeddingService(supabase, gateway=gateway)
    embedding = embedding_service.embed_version(
        EmbeddingBatchInput(
            version_id=version_id,
            document_title=title,
            chunks=chunking.chunks,
            chunking_config_hash=chunking.config_hash,
            operation_key=f"hybrid-ready:{version_id}",
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


def parse_local_bytes(payload: bytes, *, filename: str, format_key: str) -> ParseResult:
    """Parse fixture bytes through the in-process adapter.

    Args:
        payload: Exact object bytes.
        filename: Name used for temp file suffix.
        format_key: Adapter key such as ``pdf`` or ``html``.

    Returns:
        Closed parse result.
    """

    digest = hashlib.sha256(payload).hexdigest()
    with tempfile.TemporaryDirectory(prefix="hybrid-ready-") as temp_dir:
        path = Path(temp_dir) / filename
        path.write_bytes(payload)
        return parse_file(path, digest, format_key)


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
) -> HybridReadyDriveResult:
    """Persist canonical rows, project BM25, and finalize Hybrid Ready.

    Args:
        supabase_url: Local Supabase Postgres URL.
        parade_url: Packet 8 host ParadeDB writer URL.
        parse_result: Closed parser output.
        title: Document title.
        filename: Original filename.

    Returns:
        Drive outcome including public version status.
    """

    ensure_paradedb_bm25_index()
    with psycopg.connect(supabase_url) as supabase, psycopg.connect(
        parade_url, connect_timeout=8
    ) as parade:
        document_id, version_id, bm25_job_id = persist_parse_to_bm25_outbox(
            supabase,
            parse_result=parse_result,
            title=title,
            filename=filename,
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
                "SELECT status FROM app.document_versions WHERE id = %s",
                (version_id,),
            )
            row = cursor.fetchone()
        status = str(row[0]) if row is not None else "missing"
        return HybridReadyDriveResult(
            document_id=document_id,
            version_id=version_id,
            bm25_job_id=bm25_job_id,
            hybrid_ready=passed and status in {"hybrid_ready", "graph_ineligible"},
            status=status,
            detail="ok" if passed else "verify_failed",
        )
