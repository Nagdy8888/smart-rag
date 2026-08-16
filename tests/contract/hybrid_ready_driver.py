"""Drive a synthetic parse→chunk→embed→canonical→BM25 Hybrid Ready path.

Packet 8/9 contract tests and eval materialization use this helper. Embeddings
go through ``create_embedding_gateway(settings)`` so live-or-mock matches query
time. ``MOCK_MODEL_MODE=true`` (the settings default) keeps the mock adapter.
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
    settings: SharedSettings | None = None,
    visibility: str = "company_visible",
) -> tuple[UUID, UUID, UUID]:
    """Create a version, embed through the shared gateway, and enqueue BM25.

    Args:
        supabase: Open worker-capable connection (caller sets role).
        parse_result: Closed parser output for one file or merged website.
        title: Document title.
        filename: Original filename for search-term extraction.
        settings: Optional deployable settings. When omitted, mock-model mode
            is forced so Packet 8 contract tests do not inherit a live
            ``MOCK_MODEL_MODE=false`` process environment.
        visibility: ``company_visible`` or ``restricted``. Restricted gold is
            never inserted as globally public.

    Returns:
        ``(document_id, version_id, bm25_job_id)``.

    Raises:
        ValueError: If ``visibility`` is not an allow-listed enum value.

    Side Effects:
        Inserts document, version, chunks, embedding ledger, and BM25 outbox.
    """

    if visibility not in {"company_visible", "restricted"}:
        raise ValueError("visibility must be company_visible or restricted")
    document_id = uuid4()
    version_id = uuid4()
    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility)
            VALUES (%s, %s, %s::app.document_visibility)
            """,
            (document_id, title, visibility),
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


def list_persisted_chunk_texts(
    supabase: psycopg.Connection, version_id: UUID
) -> tuple[tuple[UUID, str], ...]:
    """Return persisted chunk ids and raw text for sidecar gold matching.

    Args:
        supabase: Open Postgres connection.
        version_id: Canonical version identifier.

    Returns:
        Ordered ``(chunk_id, raw_text)`` pairs.
    """

    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, raw_text
            FROM app.document_chunks
            WHERE version_id = %s
            ORDER BY chunk_index ASC
            """,
            (version_id,),
        )
        rows = cursor.fetchall()
    return tuple((UUID(str(row[0])), str(row[1] or "")) for row in rows)


def list_persisted_table_ids(
    supabase: psycopg.Connection, version_id: UUID
) -> tuple[UUID, ...]:
    """Return persisted table artifact ids for one version.

    Args:
        supabase: Open Postgres connection.
        version_id: Canonical version identifier.

    Returns:
        Table UUIDs in insert order.
    """

    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM app.document_tables
            WHERE version_id = %s
            ORDER BY created_at ASC
            """,
            (version_id,),
        )
        rows = cursor.fetchall()
    return tuple(UUID(str(row[0])) for row in rows)


def promote_graph_ineligible_current(
    supabase: psycopg.Connection,
    *,
    document_id: UUID,
    version_id: UUID,
) -> None:
    """Point retrieval RPCs at a graph-ineligible Hybrid Ready version.

    Dense/term/recheck require ``documents.current_version_id`` to equal the
    chunk version. Production ``app.finalize_hybrid_ready`` now sets that
    pointer for graph-ineligible versions. This helper remains an idempotent
    eval-driver flip when a test path skips that RPC.

    Args:
        supabase: Superuser-capable connection.
        document_id: Canonical document.
        version_id: Verified graph-ineligible version.

    Side Effects:
        Clears other ``is_current`` rows on the document, sets this version
        current, and writes ``documents.current_version_id``.
    """

    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.document_versions
            SET is_current = false, updated_at = timezone('utc', now())
            WHERE document_id = %s
              AND is_current = true
              AND id IS DISTINCT FROM %s
            """,
            (document_id, version_id),
        )
        cursor.execute(
            """
            UPDATE app.document_versions
            SET is_current = true, updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (version_id,),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s, updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (version_id, document_id),
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
) -> HybridReadyDriveResult:
    """Persist canonical rows, project BM25, and finalize Hybrid Ready.

    Args:
        supabase_url: Local Supabase Postgres URL.
        parade_url: Packet 8 host ParadeDB writer URL.
        parse_result: Closed parser output.
        title: Document title.
        filename: Original filename.
        settings: Optional settings for ``create_embedding_gateway``.
        visibility: Document visibility used at insert time.

    Returns:
        Drive outcome including public version status.
    """

    ensure_paradedb_bm25_index()
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
            promote_graph_ineligible_current(
                supabase,
                document_id=document_id,
                version_id=version_id,
            )
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
