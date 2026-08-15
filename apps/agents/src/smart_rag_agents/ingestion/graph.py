"""Phase 3 ingestion probe graph: lease validation and ledger boundary only."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypeAlias, TypedDict, cast
from uuid import UUID

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from smart_rag_core.jobs.exceptions import JobLeaseError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.jobs.ledger import JobOperationLedger

from smart_rag_agents.ingestion.checkpointer import compile_ingestion_graph


class IngestionProbeState(TypedDict):
    """Compact ingestion graph state without raw bytes or local paths.

    Attributes:
        job_id: Claimed ingestion job identifier.
        lease_token: Opaque lease token from the worker claim RPC.
        document_id: Canonical document identifier when present.
        version_id: Canonical version identifier when present.
        operation_key: Stable side-effect/idempotency key for the probe.
        storage_bucket: Durable Storage bucket reference from ``payload_ref``.
        storage_path: Durable Storage object path from ``payload_ref``.
        status: Probe lifecycle marker.
        ledger_written: Whether the boundary ledger row was recorded.
        detail: Safe diagnostic text for operators/tests.
    """

    job_id: str
    lease_token: str
    document_id: str | None
    version_id: str | None
    operation_key: str
    storage_bucket: str | None
    storage_path: str | None
    status: Literal["probe_pending", "probe_validated", "lease_invalid"]
    ledger_written: bool
    detail: str


IngestionStateGraph: TypeAlias = StateGraph[
    IngestionProbeState,
    None,
    IngestionProbeState,
    IngestionProbeState,
]
CompiledIngestionGraph: TypeAlias = CompiledStateGraph[
    IngestionProbeState,
    None,
    IngestionProbeState,
    IngestionProbeState,
]


def validate_lease(
    state: IngestionProbeState,
    config: RunnableConfig,
) -> IngestionProbeState:
    """Validate the claimed ingestion lease before any side effect.

    State inputs:
        ``job_id``, ``lease_token``.

    State outputs:
        ``status`` becomes ``probe_pending`` or ``lease_invalid``; ``detail``
        explains lease failures.

    Persistence writes:
        None.

    External/model calls:
        None.

    Budget/deadline behavior:
        None.

    Failure/fallback route:
        Invalid/expired leases set ``status=lease_invalid`` and stop the probe
        path before ledger writes.
    """

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
    return {
        **state,
        "status": "probe_pending",
        "detail": "lease validated",
    }


def boundary_probe(
    state: IngestionProbeState,
    config: RunnableConfig,
) -> IngestionProbeState:
    """Write one idempotent ledger row keyed by ``operation_key``.

    State inputs:
        Validated ``job_id``, ``lease_token``, ``operation_key``.

    State outputs:
        ``ledger_written`` and ``status=probe_validated`` on success.

    Persistence writes:
        One ``app.job_operation_ledger`` row via
        ``app.record_job_operation_ledger``.

    External/model calls:
        None.

    Budget/deadline behavior:
        None.

    Failure/fallback route:
        Lease loss raises and marks the run failed upstream; duplicate replays
        leave a single ledger row.
    """

    if state["status"] != "probe_pending":
        return state
    configurable = cast(dict[str, object], config.get("configurable", {}))
    postgres_url = configurable.get("postgres_url")
    if not isinstance(postgres_url, str):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "missing postgres configuration",
        }
    job_id = UUID(state["job_id"])
    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        ledger = JobOperationLedger(connection)
        ledger.record_completed(
            job_table="ingestion_jobs",
            job_id=job_id,
            operation_key=state["operation_key"],
            lease_token=state["lease_token"],
            result_ref={
                "probe": "phase3_packet2",
                "storage_bucket": state["storage_bucket"],
                "storage_path": state["storage_path"],
            },
        )
        connection.commit()
    return {
        **state,
        "status": "probe_validated",
        "ledger_written": True,
        "detail": "boundary probe ledger recorded",
    }


def route_after_validation(state: IngestionProbeState) -> str:
    """Route invalid leases directly to graph end."""

    if state["status"] == "lease_invalid":
        return END
    return "boundary_probe"


def build_ingestion_graph() -> IngestionStateGraph:
    """Construct the Phase 3 probe ``StateGraph`` (not yet compiled)."""

    builder: IngestionStateGraph = StateGraph(
        IngestionProbeState,
        input_schema=IngestionProbeState,
        output_schema=IngestionProbeState,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "validate_lease",
        validate_lease,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "boundary_probe",
        boundary_probe,
    )
    builder.add_edge(START, "validate_lease")
    builder.add_conditional_edges("validate_lease", route_after_validation)
    builder.add_edge("boundary_probe", END)
    return builder


def build_probe_ingestion_graph(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    interrupt_after: Sequence[str] | None = None,
) -> CompiledIngestionGraph:
    """Compile the probe graph.

    The module-level ``graph`` used by ``langgraph.json`` stays checkpointer-free
    so Studio import does not open Postgres. The worker compiles a second
    instance with ``PostgresSaver`` and ``thread_id=job_id``.

    Args:
        checkpointer: Optional durable Postgres checkpointer.
        interrupt_after: Test-only interrupt points; omitted in production.

    Returns:
        Compiled probe graph.
    """

    compiled = compile_ingestion_graph(
        build_ingestion_graph(),
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )
    return compiled  # pyright: ignore[reportReturnType]


graph: CompiledIngestionGraph = build_probe_ingestion_graph()
"""Compiled probe ingestion graph for ``langgraph.json`` registration."""
