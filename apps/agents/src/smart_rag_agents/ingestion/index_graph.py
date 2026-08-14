"""Hybrid indexing graph: parse, chunk, embed, canonical write."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from decimal import Decimal
from typing import Literal, TypeAlias, TypedDict, cast
from uuid import UUID

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.canonical.repository import CanonicalRepository
from smart_rag_core.ingestion.chunking.service import chunk_parse_result
from smart_rag_core.ingestion.embeddings.service import (
    EmbeddingBatchInput,
    EmbeddingService,
)
from smart_rag_core.ingestion.governance import ExtractionGovernanceInput
from smart_rag_core.ingestion.parser.service import ParserInvocation, ParserService
from smart_rag_core.ingestion.parser.types import ParseDisposition, ParseResult
from smart_rag_core.ingestion.parser.website import merge_website_parse_results
from smart_rag_core.jobs.exceptions import JobLeaseError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.jobs.ledger import JobOperationLedger
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    ExternalProcessingDecisionInput,
)
from smart_rag_core.settings.base import SharedSettings

from smart_rag_agents.ingestion.checkpointer import compile_ingestion_graph


class IngestionIndexState(TypedDict):
    """Indexing graph state without embeddings or raw bytes in checkpoints."""

    job_id: str
    lease_token: str
    document_id: str | None
    version_id: str | None
    operation_key: str
    storage_bucket: str | None
    storage_path: str | None
    content_hash: str | None
    byte_size: int | None
    media_type: str | None
    filename: str | None
    document_title: str | None
    declared_category: str | None
    attestation_policy_version: str | None
    review_approved: bool
    content_class: str
    graph_eligible: bool
    crawl_run_id: str | None
    status: Literal[
        "index_pending",
        "parsing",
        "index_failed",
        "indexed",
        "lease_invalid",
    ]
    chunk_set_hash: str | None
    bm25_job_id: str | None
    detail: str


IngestionIndexGraph: TypeAlias = StateGraph[
    IngestionIndexState,
    None,
    IngestionIndexState,
    IngestionIndexState,
]
CompiledIngestionIndexGraph: TypeAlias = CompiledStateGraph[
    IngestionIndexState,
    None,
    IngestionIndexState,
    IngestionIndexState,
]


def validate_index_lease(
    state: IngestionIndexState,
    config: RunnableConfig,
) -> IngestionIndexState:
    """Validate lease ownership before indexing side effects."""

    configurable = cast(dict[str, object], config.get("configurable", {}))
    postgres_url = configurable.get("postgres_url")
    lease_owner = configurable.get("lease_owner")
    lease_seconds_raw = configurable.get("job_lease_seconds", 300)
    lease_seconds = (
        int(lease_seconds_raw) if isinstance(lease_seconds_raw, int) else 300
    )
    if not isinstance(postgres_url, str) or not isinstance(lease_owner, str):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "missing postgres configuration",
        }
    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        repository = IngestionJobRepository(
            connection,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
        )
        try:
            repository.validate_active_lease(
                job_id=UUID(state["job_id"]),
                lease_token=state["lease_token"],
            )
        except JobLeaseError:
            connection.rollback()
            return {
                **state,
                "status": "lease_invalid",
                "detail": "lease validation failed",
            }
        connection.rollback()
    return {**state, "status": "index_pending", "detail": "lease validated"}


def mark_parsing_for_index(
    state: IngestionIndexState, config: RunnableConfig
) -> IngestionIndexState:
    """Transition version lifecycle to ``parsing`` before hybrid indexing."""

    if state["status"] != "index_pending" or state["version_id"] is None:
        return state
    configurable = cast(dict[str, object], config.get("configurable", {}))
    postgres_url = configurable.get("postgres_url")
    if not isinstance(postgres_url, str):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "missing postgres configuration",
        }
    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM app.document_versions WHERE id = %s",
                (UUID(state["version_id"]),),
            )
            row = cursor.fetchone()
        if row is None:
            connection.rollback()
            return {
                **state,
                "status": "index_failed",
                "detail": "version not found",
            }
        current_status = str(row[0])
        if current_status == "parsing":
            connection.rollback()
            return {**state, "status": "parsing", "detail": "status already parsing"}
        if current_status not in {"uploaded", "scanning"}:
            connection.rollback()
            return {
                **state,
                "status": "index_failed",
                "detail": f"unexpected status {current_status} before parsing",
            }
        connection.execute(
            """
            SELECT app.transition_document_version_status(
              %s, %s::app.document_status, 'parsing'::app.document_status
            )
            """,
            (UUID(state["version_id"]), current_status),
        )
        connection.commit()
    return {**state, "status": "parsing", "detail": "status parsing"}


def index_hybrid_content(
    state: IngestionIndexState, config: RunnableConfig
) -> IngestionIndexState:
    """Parse, chunk, embed, and persist canonical state plus BM25 outbox."""

    if state["status"] != "parsing":
        return state
    identity = (
        state["filename"],
        state["document_id"],
        state["version_id"],
        state["document_title"],
    )
    if any(value is None for value in identity):
        return {**state, "status": "index_failed", "detail": "missing index payload"}
    crawl_run_id = state.get("crawl_run_id")
    file_payload = (
        state["storage_bucket"],
        state["storage_path"],
        state["content_hash"],
        state["byte_size"],
    )
    if crawl_run_id is None and any(value is None for value in file_payload):
        return {**state, "status": "index_failed", "detail": "missing index payload"}

    configurable = cast(dict[str, object], config.get("configurable", {}))
    postgres_url = configurable.get("postgres_url")
    storage_url = configurable.get("storage_url")
    storage_secret = configurable.get("storage_admin_secret")
    mock_model_mode = configurable.get("mock_model_mode", True)
    if not isinstance(postgres_url, str) or not isinstance(storage_url, str):
        return {
            **state,
            "status": "index_failed",
            "detail": "missing postgres/storage config",
        }
    if not isinstance(storage_secret, str):
        return {
            **state,
            "status": "index_failed",
            "detail": "missing storage admin secret",
        }

    storage = StorageGateway(supabase_url=storage_url, admin_secret=storage_secret)
    parser = ParserService()
    governance = ExtractionGovernanceInput(
        declared_category=state["declared_category"],
        attestation_present=state["attestation_policy_version"] is not None,
        attestation_policy_version=state["attestation_policy_version"],
        review_approved=state["review_approved"],
        filename=state["filename"],
        content_class=(
            ContentClass.SYNTHETIC
            if state["content_class"] == "synthetic"
            else ContentClass.REAL_COMPANY
        ),
    )
    if isinstance(crawl_run_id, str) and crawl_run_id:
        parse_result, governance_detail, promotion_allowed = _parse_website_snapshots(
            postgres_url=postgres_url,
            storage=storage,
            parser=parser,
            crawl_run_id=UUID(crawl_run_id),
            governance=governance,
        )
        if parse_result is None:
            return {
                **state,
                "status": "index_failed",
                "detail": governance_detail,
            }
        outcome_disposition = parse_result.disposition.value
        promotion_ok = promotion_allowed
        parse_detail = parse_result.detail
        governed_parse = parse_result
    else:
        payload = storage.download_object(
            bucket=str(state["storage_bucket"]),
            object_path=str(state["storage_path"]),
        )
        if hashlib.sha256(payload).hexdigest() != str(state["content_hash"]):
            return {
                **state,
                "status": "index_failed",
                "detail": "content hash mismatch after download",
            }
        outcome = parser.parse_and_govern(
            ParserInvocation(
                payload=payload,
                content_hash=str(state["content_hash"]),
                filename=str(state["filename"]),
                media_type=state["media_type"],
            ),
            governance=governance,
            scan_evidence_current=True,
        )
        governed_parse = outcome.parse_result
        outcome_disposition = outcome.parse_result.disposition.value
        promotion_ok = outcome.promotion_allowed
        parse_detail = outcome.governance_detail or outcome.parse_result.detail

    if outcome_disposition == "failed" or not promotion_ok:
        return {
            **state,
            "status": "index_failed",
            "detail": parse_detail,
        }

    document_id = UUID(str(state["document_id"]))
    version_id = UUID(str(state["version_id"]))
    chunking = chunk_parse_result(
        governed_parse,
        document_id=document_id,
        version_id=version_id,
    )
    if not chunking.chunks:
        return {**state, "status": "index_failed", "detail": "no chunks produced"}

    settings = SharedSettings.model_construct(
        mock_model_mode=bool(mock_model_mode),
    )
    gateway = create_embedding_gateway(settings)

    governance_input = ExternalProcessingDecisionInput(
        attestation_present=state["attestation_policy_version"] is not None,
        category=CategoryDisposition.ALLOWED,
        review_approved=state["review_approved"],
        scan_evidence_current=True,
        provider_settings_verified=state["content_class"] == "synthetic",
        policy_version_matches=True,
        content_class=(
            ContentClass.SYNTHETIC
            if state["content_class"] == "synthetic"
            else ContentClass.REAL_COMPANY
        ),
    )
    embed_operation_key = f"{state['operation_key']}:embed"

    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        ledger = JobOperationLedger(connection)
        existing = ledger.fetch_result(
            job_table="ingestion_jobs",
            job_id=UUID(state["job_id"]),
            operation_key=f"{state['operation_key']}:canonical",
        )
        if existing is not None:
            connection.rollback()
            return {
                **state,
                "status": "indexed",
                "chunk_set_hash": str(existing.get("chunk_set_hash", "")),
                "bm25_job_id": str(existing.get("bm25_job_id", "")),
                "detail": "canonical ledger replay",
            }

        embedding_service = EmbeddingService(connection, gateway=gateway)
        try:
            embedding = embedding_service.embed_version(
                EmbeddingBatchInput(
                    version_id=version_id,
                    document_title=str(state["document_title"]),
                    chunks=chunking.chunks,
                    chunking_config_hash=chunking.config_hash,
                    operation_key=embed_operation_key,
                    governance=governance_input,
                    estimated_cost_usd=Decimal("0.05"),
                )
            )
        except Exception as exc:
            connection.rollback()
            return {
                **state,
                "status": "index_failed",
                "detail": str(exc)[:500],
            }

        repository = CanonicalRepository(connection)
        try:
            bm25_job_id = repository.persist_version_indexing(
                version_id=version_id,
                document_id=document_id,
                document_title=str(state["document_title"]),
                filename=state["filename"],
                chunking=chunking,
                embedding=embedding,
                embedded=embedding.embedded,
                table_artifacts=chunking.table_artifacts,
                is_current=not state["graph_eligible"],
            )
        except Exception as exc:
            connection.rollback()
            return {
                **state,
                "status": "index_failed",
                "detail": str(exc)[:500],
            }

        ledger.record_completed(
            job_table="ingestion_jobs",
            job_id=UUID(state["job_id"]),
            operation_key=f"{state['operation_key']}:canonical",
            lease_token=state["lease_token"],
            result_ref={
                "chunk_set_hash": embedding.chunk_set_hash,
                "bm25_job_id": str(bm25_job_id),
                "embedding_ledger_id": str(embedding.ledger_id),
            },
        )
        connection.commit()

    return {
        **state,
        "status": "indexed",
        "chunk_set_hash": embedding.chunk_set_hash,
        "bm25_job_id": str(bm25_job_id),
        "detail": "canonical persisted; bm25 projection pending",
    }


def _parse_website_snapshots(
    *,
    postgres_url: str,
    storage: StorageGateway,
    parser: ParserService,
    crawl_run_id: UUID,
    governance: ExtractionGovernanceInput,
) -> tuple[ParseResult | None, str, bool]:
    """Parse every snapshot for one crawl run into a single element tree.

    Args:
        postgres_url: Worker-role database URL.
        storage: Privileged Storage gateway for snapshot bytes.
        parser: Sandboxed parser service.
        crawl_run_id: Durable crawl run identifier.
        governance: Extraction governance input shared across pages.

    Returns:
        Tuple of merged parse result (or ``None``), diagnostic detail, and
        whether promotion/indexing is allowed.
    """

    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT storage_bucket, storage_path, content_hash, canonical_url,
                       content_type
                FROM app.web_snapshots
                WHERE crawl_run_id = %s
                ORDER BY fetched_at, created_at
                """,
                (crawl_run_id,),
            )
            rows = cursor.fetchall()
        connection.rollback()
    if not rows:
        return None, "no snapshots for crawl run", False
    pages: list[ParseResult] = []
    hashes: list[str] = []
    for row in rows:
        bucket, path, content_hash, canonical_url, content_type = row
        payload = storage.download_object(bucket=str(bucket), object_path=str(path))
        digest = hashlib.sha256(payload).hexdigest()
        if digest != str(content_hash):
            return None, "snapshot content hash mismatch after download", False
        hashes.append(digest)
        filename = str(canonical_url).rsplit("/", 1)[-1] or "index.html"
        if "." not in filename:
            filename = f"{filename}.html"
        outcome = parser.parse_and_govern(
            ParserInvocation(
                payload=payload,
                content_hash=str(content_hash),
                filename=filename,
                media_type=str(content_type) if content_type else "text/html",
            ),
            governance=governance,
            scan_evidence_current=True,
        )
        if (
            outcome.parse_result.disposition is ParseDisposition.FAILED
            or not outcome.promotion_allowed
        ):
            return (
                None,
                outcome.governance_detail or outcome.parse_result.detail,
                False,
            )
        pages.append(outcome.parse_result)
    combined = hashlib.sha256("".join(hashes).encode("utf-8")).hexdigest()
    merged = merge_website_parse_results(tuple(pages), combined_hash=combined)
    if merged.disposition is ParseDisposition.FAILED:
        return None, merged.detail, False
    return merged, merged.detail, True


def route_after_index_lease(state: IngestionIndexState) -> str:
    """Route invalid leases directly to graph end."""

    if state["status"] == "lease_invalid":
        return END
    return "mark_parsing_for_index"


def route_after_index(state: IngestionIndexState) -> str:
    """End graph after indexing completes or fails."""

    return END


def build_index_graph() -> IngestionIndexGraph:
    """Construct hybrid indexing ``StateGraph`` (not yet compiled)."""

    builder: IngestionIndexGraph = StateGraph(
        IngestionIndexState,
        input_schema=IngestionIndexState,
        output_schema=IngestionIndexState,
    )
    builder.add_node("validate_index_lease", validate_index_lease)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("mark_parsing_for_index", mark_parsing_for_index)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("index_hybrid_content", index_hybrid_content)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "validate_index_lease")
    builder.add_conditional_edges("validate_index_lease", route_after_index_lease)
    builder.add_edge("mark_parsing_for_index", "index_hybrid_content")
    builder.add_conditional_edges("index_hybrid_content", route_after_index)
    return builder


def build_index_ingestion_graph(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    interrupt_after: Sequence[str] | None = None,
) -> CompiledIngestionIndexGraph:
    """Compile hybrid indexing graph.

    Args:
        checkpointer: Optional Postgres checkpointer used by the worker.
        interrupt_after: Test-only interrupt points.

    Returns:
        Compiled hybrid indexing graph.
    """

    compiled = compile_ingestion_graph(
        build_index_graph(),
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )
    return compiled  # pyright: ignore[reportReturnType]
