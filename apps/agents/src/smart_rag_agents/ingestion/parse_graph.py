"""Phase 3 parse ingestion graph nodes."""

from __future__ import annotations

import hashlib
from typing import Literal, TypeAlias, TypedDict, cast
from uuid import UUID

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.governance import ExtractionGovernanceInput
from smart_rag_core.ingestion.parser.service import ParserInvocation, ParserService
from smart_rag_core.jobs.exceptions import JobLeaseError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.security.external_processing import ContentClass


class IngestionParseState(TypedDict):
    """Parse graph state without durable local paths in checkpoints."""

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
    declared_category: str | None
    attestation_policy_version: str | None
    review_approved: bool
    content_class: str
    status: Literal[
        "parse_pending",
        "parsing",
        "parse_failed",
        "parsed",
        "lease_invalid",
    ]
    parse_disposition: str | None
    promotion_allowed: bool
    detail: str


IngestionParseGraph: TypeAlias = StateGraph[
    IngestionParseState,
    None,
    IngestionParseState,
    IngestionParseState,
]
CompiledIngestionParseGraph: TypeAlias = CompiledStateGraph[
    IngestionParseState,
    None,
    IngestionParseState,
    IngestionParseState,
]


def validate_parse_lease(
    state: IngestionParseState,
    config: RunnableConfig,
) -> IngestionParseState:
    """Validate lease ownership before parser side effects."""

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
    return {**state, "status": "parse_pending", "detail": "lease validated"}


def mark_parsing(
    state: IngestionParseState, config: RunnableConfig
) -> IngestionParseState:
    """Transition version lifecycle to ``parsing``."""

    if state["status"] != "parse_pending" or state["version_id"] is None:
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
        connection.execute(
            """
            SELECT app.transition_document_version_status(
              %s, 'uploaded'::app.document_status, 'parsing'::app.document_status
            )
            """,
            (UUID(state["version_id"]),),
        )
        connection.commit()
    return {**state, "status": "parsing", "detail": "status parsing"}


def parse_and_govern(
    state: IngestionParseState, config: RunnableConfig
) -> IngestionParseState:
    """Download object bytes, parse in sandbox, and run extraction governance."""

    if state["status"] != "parsing":
        return state
    required = (
        state["storage_bucket"],
        state["storage_path"],
        state["content_hash"],
        state["byte_size"],
        state["filename"],
    )
    if any(value is None for value in required):
        return {**state, "status": "parse_failed", "detail": "missing parse payload"}

    configurable = cast(dict[str, object], config.get("configurable", {}))
    storage_url = configurable.get("storage_url")
    storage_secret = configurable.get("storage_admin_secret")
    if not isinstance(storage_url, str) or not isinstance(storage_secret, str):
        return {
            **state,
            "status": "parse_failed",
            "detail": "missing storage configuration",
        }

    storage = StorageGateway(supabase_url=storage_url, admin_secret=storage_secret)
    payload = storage.download_object(
        bucket=str(state["storage_bucket"]),
        object_path=str(state["storage_path"]),
    )
    if hashlib.sha256(payload).hexdigest() != str(state["content_hash"]):
        return {
            **state,
            "status": "parse_failed",
            "detail": "content hash mismatch after download",
        }
    if len(payload) != int(cast(int, state["byte_size"])):
        return {
            **state,
            "status": "parse_failed",
            "detail": "byte size mismatch after download",
        }
    service = ParserService()
    outcome = service.parse_and_govern(
        ParserInvocation(
            payload=payload,
            content_hash=str(state["content_hash"]),
            filename=str(state["filename"]),
            media_type=state["media_type"],
        ),
        governance=ExtractionGovernanceInput(
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
        ),
        scan_evidence_current=True,
    )
    if (
        outcome.parse_result.disposition.value == "failed"
        or not outcome.promotion_allowed
    ):
        return {
            **state,
            "status": "parse_failed",
            "parse_disposition": outcome.parse_result.disposition.value,
            "promotion_allowed": False,
            "detail": outcome.governance_detail or outcome.parse_result.detail,
        }
    return {
        **state,
        "status": "parsed",
        "parse_disposition": outcome.parse_result.disposition.value,
        "promotion_allowed": outcome.promotion_allowed,
        "detail": "parse and governance passed",
    }


def route_after_parse_lease(state: IngestionParseState) -> str:
    """Route invalid leases to graph end."""

    if state["status"] == "lease_invalid":
        return END
    return "mark_parsing"


def route_after_parse(state: IngestionParseState) -> str:
    """End graph after parse failure."""

    if state["status"] == "parse_failed":
        return END
    return END


def build_parse_graph() -> IngestionParseGraph:
    """Construct parse ``StateGraph`` (not yet compiled)."""

    builder: IngestionParseGraph = StateGraph(
        IngestionParseState,
        input_schema=IngestionParseState,
        output_schema=IngestionParseState,
    )
    builder.add_node("validate_parse_lease", validate_parse_lease)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("mark_parsing", mark_parsing)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("parse_and_govern", parse_and_govern)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "validate_parse_lease")
    builder.add_conditional_edges("validate_parse_lease", route_after_parse_lease)
    builder.add_edge("mark_parsing", "parse_and_govern")
    builder.add_conditional_edges("parse_and_govern", route_after_parse)
    return builder


def build_parse_ingestion_graph() -> CompiledIngestionParseGraph:
    """Compile parse graph without checkpointer."""

    return build_parse_graph().compile()  # pyright: ignore[reportUnknownMemberType]
