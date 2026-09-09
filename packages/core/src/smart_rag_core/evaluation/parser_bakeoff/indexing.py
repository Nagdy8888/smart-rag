"""Evaluation-owned isolated document/version indexing for the bake-off."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    DOCUMENT_TITLE_PREFIX,
    LaneId,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffScanEvidence,
    LaneIngestIds,
)
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.ingestion.canonical.repository import CanonicalRepository
from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.embeddings.service import (
    EmbeddingBatchInput,
    EmbeddingService,
)
from smart_rag_core.ingestion.limits import SCAN_CONFIG_VERSION
from smart_rag_core.ingestion.parser.types import ParseDisposition, ParseResult
from smart_rag_core.ingestion.scan import ObjectScanResult
from smart_rag_core.release.hybrid import mark_bm25_job_processing
from smart_rag_core.repositories.scan_events import ScanEventRepository
from smart_rag_core.schema.enums import ScanResult
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    ExternalProcessingDecisionInput,
)
from smart_rag_core.settings import SharedSettings


def lane_document_title(run_id: str, lane_id: LaneId) -> str:
    """Return the exact restricted document title for one lane.

    Args:
        run_id: Bake-off run identifier.
        lane_id: Lane token.

    Returns:
        ``parser-bakeoff:<run-id>:<lane>``.
    """

    return f"{DOCUMENT_TITLE_PREFIX}:{run_id}:{lane_id}"


def assert_title_owned(*, title: str, run_id: str, lane_id: LaneId) -> None:
    """Refuse deletion or reuse when the title is not this run's prefix.

    Args:
        title: Stored document title.
        run_id: Expected run identifier.
        lane_id: Expected lane.

    Raises:
        BakeoffError: When the title does not match exactly.
    """

    expected = lane_document_title(run_id, lane_id)
    if title != expected:
        raise BakeoffError(
            "cleanup_title_mismatch", "document title is not owned by this run"
        )


def _scan_from_evidence(
    evidence: BakeoffScanEvidence, *, object_hash: str
) -> ObjectScanResult:
    """Adapt bake-off scan evidence into a repository payload.

    Args:
        evidence: Manifest ClamAV evidence.
        object_hash: Source SHA-256.

    Returns:
        Append-only scan payload.

    Raises:
        BakeoffError: When the recorded disposition is not clean.
    """

    if evidence.disposition != ScanResult.CLEAN.value:
        raise BakeoffError("scan_not_clean", "index requires a clean scan")
    return ObjectScanResult(
        result=ScanResult.CLEAN,
        object_hash=object_hash,
        bytes_examined=evidence.bytes_examined,
        scan_engine_version=evidence.engine_version,
        signature_version=evidence.signature_version,
        functionality_level="full",
        signature_db_timestamp=None,
        signature_db_ids=dict(evidence.signature_db_ids),
        config_version=SCAN_CONFIG_VERSION,
        details={"source": "parser_bakeoff", "detail": evidence.detail},
    )


def persist_lane_index(
    supabase: psycopg.Connection,
    parade: psycopg.Connection,
    *,
    parse_result: ParseResult,
    run_id: str,
    lane_id: LaneId,
    filename: str,
    source_sha256: str,
    scan: BakeoffScanEvidence,
    actor_id: UUID,
    settings: SharedSettings,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
) -> LaneIngestIds:
    """Persist one restricted graph-ineligible lane and project BM25.

    Args:
        supabase: Worker-capable Supabase connection.
        parade: ParadeDB writer connection.
        parse_result: Closed parse for this lane.
        run_id: Run identifier used in the document title.
        lane_id: Lane token.
        filename: Original PDF basename.
        source_sha256: Shared PDF hash.
        scan: Clean ClamAV evidence for the exact source hash.
        actor_id: Restricted ACL grantee required by sealed cases.
        settings: Shared settings for the embedding gateway.
        document_id: Optional pre-allocated document UUID.
        version_id: Optional pre-allocated version UUID.

    Returns:
        Written ingest identifiers.

    Raises:
        BakeoffError: When the parse failed, scan is not clean, BM25 verify
            fails, or the version is graph-eligible.

    Side Effects:
        Inserts document, ACL, scan evidence, chunks, embeddings, and BM25 rows.
    """

    if parse_result.disposition is ParseDisposition.FAILED:
        raise BakeoffError("lane_parse_failed", "refusing to index a failed parse")
    if parse_result.content_hash != source_sha256:
        raise BakeoffError("hash_mismatch", "parse hash does not match the run source")
    title = lane_document_title(run_id, lane_id)
    document_id = document_id or uuid4()
    version_id = version_id or uuid4()
    supabase.execute("SET ROLE postgres")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, graph_eligible)
            VALUES (%s, %s, 'restricted'::app.document_visibility, false)
            """,
            (document_id, title),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status, graph_eligible
            )
            VALUES (%s, %s, 1, 'parsing', false)
            """,
            (version_id, document_id),
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
        cursor.execute(
            """
            INSERT INTO app.document_acl (document_id, grantee_user_id, granted_by)
            VALUES (%s, %s, %s)
            """,
            (document_id, actor_id, actor_id),
        )
    scan_payload = _scan_from_evidence(scan, object_hash=source_sha256)
    ScanEventRepository(supabase).insert_scan_event(
        document_id=document_id,
        version_id=version_id,
        uploader_user_id=actor_id,
        session_id=None,
        declared_category="company_internal",
        scan=scan_payload,
    )
    supabase.execute("SET ROLE app_worker")
    chunking = chunk_parse_result(
        parse_result, document_id=document_id, version_id=version_id
    )
    gateway = create_embedding_gateway(settings)
    embedding_service = EmbeddingService(supabase, gateway=gateway)
    embedding = embedding_service.embed_version(
        EmbeddingBatchInput(
            version_id=version_id,
            document_title=title,
            chunks=chunking.chunks,
            chunking_config_hash=chunking.config_hash,
            operation_key=f"parser-bakeoff:{run_id}:{lane_id}:{version_id}",
            governance=ExternalProcessingDecisionInput(
                attestation_present=True,
                category=CategoryDisposition.ALLOWED,
                review_approved=True,
                scan_evidence_current=True,
                provider_settings_verified=True,
                policy_version_matches=True,
                content_class=ContentClass.REAL_COMPANY,
            ),
            estimated_cost_usd=Decimal("0.05"),
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
    supabase.execute("SET ROLE app_worker")
    mark_bm25_job_processing(supabase, bm25_job_id)
    supabase.commit()
    parade.execute("SET ROLE paradedb_writer")
    service = Bm25ProjectionService(supabase, parade)
    passed = service.process_upsert_job(version_id=version_id, job_id=bm25_job_id)
    if passed:
        supabase.commit()
        parade.commit()
    else:
        supabase.rollback()
        parade.rollback()
        raise BakeoffError("bm25_verify_failed", "BM25 projection did not verify")
    supabase.execute("RESET ROLE")
    with supabase.cursor() as cursor:
        cursor.execute(
            """
            SELECT status::text, graph_eligible
            FROM app.document_versions
            WHERE id = %s
            """,
            (version_id,),
        )
        status_row = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM app.document_chunks WHERE version_id = %s",
            (version_id,),
        )
        count_row = cursor.fetchone()
    status = str(status_row[0]) if status_row is not None else "missing"
    graph_eligible = bool(status_row[1]) if status_row is not None else True
    if graph_eligible:
        raise BakeoffError(
            "graph_eligible", "bake-off versions must stay graph-ineligible"
        )
    chunk_count = int(count_row[0]) if count_row is not None else 0
    ready_states = {"hybrid_ready", "graph_ineligible", "graph_pending"}
    hybrid_ready = passed and status in ready_states
    if not hybrid_ready:
        raise BakeoffError("hybrid_not_ready", f"unexpected version status {status}")
    return LaneIngestIds(
        lane_id=lane_id,
        document_id=document_id,
        version_id=version_id,
        title=title,
        bm25_job_id=bm25_job_id,
        status=status,
        hybrid_ready=hybrid_ready,
        chunk_count=chunk_count,
        graph_eligible=False,
    )
