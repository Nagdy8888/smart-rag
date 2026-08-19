"""Phase 3 scan-and-promote ingestion graph nodes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypeAlias, TypedDict, cast
from uuid import UUID

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from smart_rag_core.gateways.clamav import ClamAvClient
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.governance import (
    MetadataGovernanceInput,
    evaluate_metadata_governance,
)
from smart_rag_core.ingestion.promotion import (
    PromotionContext,
    PromotionSaga,
    PromotionSagaError,
    PromotionStep,
)
from smart_rag_core.ingestion.scan import ObjectScanInput, scan_object_bytes
from smart_rag_core.jobs.exceptions import JobLeaseError
from smart_rag_core.jobs.hybrid_enqueue import enqueue_hybrid_index_job
from smart_rag_core.jobs.ingestion_repository import (
    IngestionJobRepository,
    configurable_lease_lost,
)
from smart_rag_core.observability.ingest_progress import log_ingest_progress
from smart_rag_core.repositories.notifications import AdminNotificationRepository
from smart_rag_core.repositories.scan_events import ScanEventRepository
from smart_rag_core.schema.enums import ScanResult
from smart_rag_core.security.external_processing import (
    ContentClass as GovernanceContentClass,
)

from smart_rag_agents.ingestion.checkpointer import compile_ingestion_graph


class IngestionScanState(TypedDict):
    """Compact scan/promote graph state without raw bytes or local paths."""

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
    destination_bucket: str | None
    destination_path: str | None
    reservation_id: str | None
    declared_category: str | None
    attestation_policy_version: str | None
    uploader_user_id: str | None
    review_approved: bool
    content_class: str
    crash_after: str | None
    status: Literal[
        "scan_pending",
        "scanning",
        "scan_failed",
        "promotion_failed",
        "promoted",
        "lease_invalid",
    ]
    scan_result: str | None
    detail: str


IngestionScanGraph: TypeAlias = StateGraph[
    IngestionScanState,
    None,
    IngestionScanState,
    IngestionScanState,
]
CompiledIngestionScanGraph: TypeAlias = CompiledStateGraph[
    IngestionScanState,
    None,
    IngestionScanState,
    IngestionScanState,
]


def validate_scan_lease(
    state: IngestionScanState,
    config: RunnableConfig,
) -> IngestionScanState:
    """Validate lease ownership before scan side effects.

    State inputs:
        ``job_id``, ``lease_token``.

    State outputs:
        ``status`` ``scan_pending`` or ``lease_invalid``.

    Persistence writes:
        None.

    External/model calls:
        None.

    Budget/deadline behavior:
        ``configurable.lease_lost`` aborts before scanning.

    Failure/fallback route:
        Invalid/expired/lost leases skip ClamAV and promotion.
    """

    if configurable_lease_lost(config):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "lease lost",
        }
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
    return {**state, "status": "scan_pending", "detail": "lease validated"}


def mark_scanning(
    state: IngestionScanState, config: RunnableConfig
) -> IngestionScanState:
    """Transition version lifecycle to ``scanning``.

    State inputs:
        ``scan_pending`` status and ``version_id``.

    State outputs:
        ``status`` ``scanning`` or unchanged.

    Persistence writes:
        Version status ``uploaded`` → ``scanning``.

    External/model calls:
        None.

    Budget/deadline behavior:
        Lease-lost aborts without a write.

    Failure/fallback route:
        Missing version id leaves state unchanged.
    """

    if configurable_lease_lost(config):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "lease lost",
        }
    if state["status"] != "scan_pending" or state["version_id"] is None:
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
              %s, 'uploaded'::app.document_status, 'scanning'::app.document_status
            )
            """,
            (UUID(state["version_id"]),),
        )
        connection.commit()
    return {**state, "status": "scanning", "detail": "status scanning"}


def scan_and_govern(
    state: IngestionScanState, config: RunnableConfig
) -> IngestionScanState:
    """Download exact object bytes, scan with ClamAV, persist evidence, govern.

    State inputs:
        ``scanning`` status and durable Storage refs.

    State outputs:
        ``scan_result`` and ``status`` remaining ``scanning`` or ``scan_failed``.

    Persistence writes:
        Append-only ``document_scan_events``; admin notifications on failure.

    External/model calls:
        ClamAV INSTREAM on exact object bytes.

    Budget/deadline behavior:
        Lease-lost aborts before download.

    Failure/fallback route:
        Dirty/unscannable/stale scans fail closed. Never fake clean.
    """

    if configurable_lease_lost(config):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "lease lost",
        }
    if state["status"] != "scanning":
        return state
    required = (
        state["storage_bucket"],
        state["storage_path"],
        state["content_hash"],
        state["byte_size"],
        state["document_id"],
        state["version_id"],
    )
    if any(value is None for value in required):
        return {**state, "status": "scan_failed", "detail": "missing scan payload"}

    log_ingest_progress("hybrid", "scan", UUID(str(state["job_id"])))

    byte_size_value = cast(int, state["byte_size"])
    configurable = cast(dict[str, object], config.get("configurable", {}))
    postgres_url = configurable.get("postgres_url")
    storage_url = configurable.get("storage_url")
    storage_secret = configurable.get("storage_admin_secret")
    clamav_host = configurable.get("clamav_host", "clamav")
    clamav_port_raw = configurable.get("clamav_port", 3310)
    clamav_port = int(clamav_port_raw) if isinstance(clamav_port_raw, int) else 3310
    if not isinstance(postgres_url, str) or not isinstance(storage_url, str):
        return {
            **state,
            "status": "scan_failed",
            "detail": "missing storage/postgres config",
        }
    if not isinstance(storage_secret, str):
        return {
            **state,
            "status": "scan_failed",
            "detail": "missing storage admin secret",
        }

    storage = StorageGateway(supabase_url=storage_url, admin_secret=storage_secret)
    clamav = ClamAvClient(host=str(clamav_host), port=clamav_port)
    byte_size = int(byte_size_value)
    scan = scan_object_bytes(
        storage,
        clamav,
        ObjectScanInput(
            bucket=str(state["storage_bucket"]),
            path=str(state["storage_path"]),
            expected_hash=str(state["content_hash"]),
            expected_bytes=byte_size,
        ),
    )

    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        scan_repo = ScanEventRepository(connection)
        scan_repo.insert_scan_event(
            document_id=UUID(str(state["document_id"])),
            version_id=UUID(str(state["version_id"])),
            uploader_user_id=(
                UUID(state["uploader_user_id"]) if state["uploader_user_id"] else None
            ),
            session_id=None,
            declared_category=state["declared_category"],
            scan=scan,
        )
        if scan.result is not ScanResult.CLEAN:
            notifications = AdminNotificationRepository(connection)
            notifications.emit(
                kind="repeated_scan_failure",
                severity="warning",
                title="Quarantine scan failed",
                body=f"Scan result {scan.result.value} for version {state['version_id']}",
                metadata={
                    "version_id": state["version_id"],
                    "result": scan.result.value,
                    "detail": scan.details,
                },
            )
            connection.commit()
            return {
                **state,
                "status": "scan_failed",
                "scan_result": scan.result.value,
                "detail": str(scan.details.get("detail", scan.result.value)),
            }

        governance = evaluate_metadata_governance(
            MetadataGovernanceInput(
                declared_category=state["declared_category"],
                attestation_present=state["attestation_policy_version"] is not None,
                attestation_policy_version=state["attestation_policy_version"],
                review_approved=state["review_approved"],
                filename=str(state["storage_path"]).split("/")[-1],
                content_class=(
                    GovernanceContentClass.SYNTHETIC
                    if state["content_class"] == "synthetic"
                    else GovernanceContentClass.REAL_COMPANY
                ),
            ),
            scan_evidence_current=True,
        )
        if not governance.promotion_allowed:
            notifications = AdminNotificationRepository(connection)
            notifications.emit(
                kind="quarantine_accumulation",
                severity="warning",
                title="Promotion blocked by governance",
                body=governance.detail,
                metadata={
                    "version_id": state["version_id"],
                    "category": governance.category.value,
                },
            )
            connection.commit()
            return {
                **state,
                "status": "scan_failed",
                "scan_result": scan.result.value,
                "detail": governance.detail,
            }
        connection.commit()

    return {
        **state,
        "status": "scanning",
        "scan_result": scan.result.value,
        "detail": "scan clean; promotion pending",
    }


def promote_object(
    state: IngestionScanState, config: RunnableConfig
) -> IngestionScanState:
    """Run the resumable Storage promotion saga when scan/governance passed.

    State inputs:
        Clean ``scan_result`` and promotion Storage refs.

    State outputs:
        ``promoted`` or ``promotion_failed``.

    Persistence writes:
        Promotion saga ledger, hybrid_index enqueue.

    External/model calls:
        Storage copy/verify/delete.

    Budget/deadline behavior:
        Lease-lost aborts before saga.

    Failure/fallback route:
        Saga errors alert and fail the job.
    """

    if configurable_lease_lost(config):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "lease lost",
        }
    if state["scan_result"] != ScanResult.CLEAN.value:
        return state
    required = (
        state["version_id"],
        state["storage_bucket"],
        state["storage_path"],
        state["destination_bucket"],
        state["destination_path"],
        state["content_hash"],
        state["byte_size"],
    )
    if any(value is None for value in required):
        return {
            **state,
            "status": "promotion_failed",
            "detail": "missing promotion payload",
        }

    byte_size_value = cast(int, state["byte_size"])
    promote_bytes = int(byte_size_value)
    configurable = cast(dict[str, object], config.get("configurable", {}))
    postgres_url = configurable.get("postgres_url")
    storage_url = configurable.get("storage_url")
    storage_secret = configurable.get("storage_admin_secret")
    if not isinstance(postgres_url, str) or not isinstance(storage_url, str):
        return {
            **state,
            "status": "promotion_failed",
            "detail": "missing postgres/storage config",
        }
    if not isinstance(storage_secret, str):
        return {
            **state,
            "status": "promotion_failed",
            "detail": "missing storage admin secret",
        }

    crash_step: PromotionStep | None = None
    if state.get("crash_after"):
        try:
            crash_step = PromotionStep(str(state["crash_after"]))
        except ValueError:
            crash_step = None
    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        saga = PromotionSaga(
            connection,
            StorageGateway(supabase_url=storage_url, admin_secret=storage_secret),
        )
        try:
            saga.run(
                PromotionContext(
                    saga_idempotency_key=f"{state['operation_key']}:promotion",
                    version_id=UUID(str(state["version_id"])),
                    reservation_id=(
                        UUID(state["reservation_id"])
                        if state["reservation_id"]
                        else None
                    ),
                    quarantine_bucket=str(state["storage_bucket"]),
                    quarantine_path=str(state["storage_path"]),
                    destination_bucket=str(state["destination_bucket"]),
                    destination_path=str(state["destination_path"]),
                    expected_hash=str(state["content_hash"]),
                    expected_bytes=promote_bytes,
                    media_type=state["media_type"],
                    crash_after=crash_step,
                )
            )
        except PromotionSagaError as exc:
            notifications = AdminNotificationRepository(connection)
            notifications.emit(
                kind="quarantine_accumulation",
                severity="critical",
                title="Promotion saga failed",
                body=str(exc)[:500],
                metadata={"version_id": state["version_id"]},
            )
            connection.commit()
            return {**state, "status": "promotion_failed", "detail": str(exc)}
        document_id = UUID(str(state["document_id"])) if state["document_id"] else None
        version_id = UUID(str(state["version_id"]))
        graph_eligible = False
        document_title = "document"
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT d.title, dv.graph_eligible
                FROM app.document_versions AS dv
                JOIN app.documents AS d ON d.id = dv.document_id
                WHERE dv.id = %s
                """,
                (version_id,),
            )
            meta = cursor.fetchone()
            if meta is not None:
                document_title = str(meta[0])
                graph_eligible = bool(meta[1])
        if document_id is None:
            connection.rollback()
            return {
                **state,
                "status": "promotion_failed",
                "detail": "missing document_id for hybrid_index enqueue",
            }
        destination_path = str(state["destination_path"])
        filename = destination_path.rsplit("/", 1)[-1]
        enqueue_hybrid_index_job(
            connection,
            document_id=document_id,
            version_id=version_id,
            estimated_size_bytes=promote_bytes,
            payload_ref={
                "storage_bucket": str(state["destination_bucket"]),
                "storage_path": destination_path,
                "content_hash": str(state["content_hash"]),
                "byte_size": promote_bytes,
                "media_type": state["media_type"],
                "filename": filename,
                "document_title": document_title,
                "declared_category": state["declared_category"],
                "attestation_policy_version": state["attestation_policy_version"],
                "review_approved": state["review_approved"],
                "content_class": state["content_class"],
                "graph_eligible": graph_eligible,
            },
        )
        connection.commit()
    return {**state, "status": "promoted", "detail": "promotion completed"}


def route_after_scan_lease(state: IngestionScanState) -> str:
    """Route invalid leases to graph end."""

    if state["status"] == "lease_invalid":
        return END
    return "mark_scanning"


def route_after_scan(state: IngestionScanState) -> str:
    """Route failed scans to end; clean scans continue to promotion."""

    if state["status"] == "scan_failed":
        return END
    return "promote_object"


def build_scan_promote_graph() -> IngestionScanGraph:
    """Construct scan/promote ``StateGraph`` (not yet compiled)."""

    builder: IngestionScanGraph = StateGraph(
        IngestionScanState,
        input_schema=IngestionScanState,
        output_schema=IngestionScanState,
    )
    builder.add_node("validate_scan_lease", validate_scan_lease)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("mark_scanning", mark_scanning)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("scan_and_govern", scan_and_govern)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("promote_object", promote_object)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "validate_scan_lease")
    builder.add_conditional_edges("validate_scan_lease", route_after_scan_lease)
    builder.add_edge("mark_scanning", "scan_and_govern")
    builder.add_conditional_edges("scan_and_govern", route_after_scan)
    builder.add_edge("promote_object", END)
    return builder


def build_scan_promote_ingestion_graph(
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    interrupt_after: Sequence[str] | None = None,
) -> CompiledIngestionScanGraph:
    """Compile scan/promote graph.

    Args:
        checkpointer: Optional Postgres checkpointer used by the worker.
        interrupt_after: Test-only interrupt points.

    Returns:
        Compiled scan/promote graph.
    """

    compiled = compile_ingestion_graph(
        build_scan_promote_graph(),
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )
    return compiled  # pyright: ignore[reportReturnType]
