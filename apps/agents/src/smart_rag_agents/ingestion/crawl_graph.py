"""Phase 3 approved website crawl graph nodes."""

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
from smart_rag_core.gateways.crawl_proxy import CrawlProxyGateway
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.crawl.adapter import (
    BoundedCrawlAdapter,
    WebSnapshotRecord,
)
from smart_rag_core.ingestion.crawl.exceptions import (
    CrawlLimitExceeded,
    CrawlPolicyError,
)
from smart_rag_core.ingestion.scan import ObjectScanInput, scan_object_bytes
from smart_rag_core.jobs.exceptions import JobLeaseError
from smart_rag_core.jobs.hybrid_enqueue import enqueue_hybrid_index_job
from smart_rag_core.jobs.ingestion_repository import (
    IngestionJobRepository,
    configurable_lease_lost,
)
from smart_rag_core.repositories.crawl import CrawlRepository
from smart_rag_core.repositories.scan_events import ScanEventRepository
from smart_rag_core.schema.enums import ScanResult

from smart_rag_agents.ingestion.checkpointer import compile_ingestion_graph


class IngestionCrawlState(TypedDict):
    """Compact crawl graph state without raw page bytes."""

    job_id: str
    lease_token: str
    source_id: str | None
    version_id: str | None
    operation_key: str
    content_class: str
    graph_eligible: bool
    attestation_policy_version: str | None
    status: Literal["crawl_pending", "crawl_completed", "crawl_failed", "lease_invalid"]
    pages_fetched: int
    crawl_run_id: str | None
    detail: str


IngestionCrawlGraph: TypeAlias = StateGraph[
    IngestionCrawlState,
    None,
    IngestionCrawlState,
    IngestionCrawlState,
]
CompiledIngestionCrawlGraph: TypeAlias = CompiledStateGraph[
    IngestionCrawlState,
    None,
    IngestionCrawlState,
    IngestionCrawlState,
]


def validate_crawl_lease(
    state: IngestionCrawlState,
    config: RunnableConfig,
) -> IngestionCrawlState:
    """Validate lease ownership before crawl side effects.

    State inputs:
        ``job_id``, ``lease_token``.

    State outputs:
        ``status`` becomes ``crawl_pending`` or ``lease_invalid``.

    Persistence writes:
        None.

    External/model calls:
        None.

    Budget/deadline behavior:
        None. Heartbeat lease loss sets ``configurable.lease_lost``.

    Failure/fallback route:
        Invalid/expired/lost leases set ``status=lease_invalid`` and skip crawl.
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
    return {**state, "status": "crawl_pending", "detail": "lease validated"}


def execute_approved_crawl(
    state: IngestionCrawlState,
    config: RunnableConfig,
) -> IngestionCrawlState:
    """Run bounded crawl, ClamAV-scan snapshots, then enqueue hybrid_index.

    State inputs:
        Validated ``source_id``, ``version_id``, crawl bounds from approval.

    State outputs:
        ``status`` ``crawl_completed`` or ``crawl_failed``; ``crawl_run_id``
        and ``pages_fetched`` on completion.

    Persistence writes:
        Crawl run/snapshot rows, ``document_scan_events``, and one
        ``hybrid_index`` job only after every snapshot has a current clean
        scan.

    External/model calls:
        Crawl proxy fetches; ClamAV ``INSTREAM`` per snapshot. No embeddings.

    Budget/deadline behavior:
        Lease re-check and ``lease_lost`` abort before enqueue.

    Failure/fallback route:
        Missing/dirty scan fails the crawl job and does not enqueue
        ``hybrid_index``. Fake clean scan success is forbidden.
    """

    if configurable_lease_lost(config):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "lease lost",
        }
    if state["status"] != "crawl_pending" or state["source_id"] is None:
        return state
    configurable = cast(dict[str, object], config.get("configurable", {}))
    postgres_url = configurable.get("postgres_url")
    crawl_proxy_url = configurable.get("crawl_proxy_url")
    storage_url = configurable.get("storage_url")
    storage_secret = configurable.get("storage_admin_secret")
    if not isinstance(postgres_url, str):
        return {
            **state,
            "status": "lease_invalid",
            "detail": "missing postgres configuration",
        }
    if not isinstance(crawl_proxy_url, str):
        return {
            **state,
            "status": "crawl_failed",
            "detail": "missing crawl proxy url",
        }
    source_id = UUID(state["source_id"])
    version_id = UUID(state["version_id"]) if state["version_id"] else None
    storage = None
    if isinstance(storage_url, str) and isinstance(storage_secret, str):
        storage = StorageGateway(supabase_url=storage_url, admin_secret=storage_secret)
    proxy = CrawlProxyGateway(proxy_base_url=crawl_proxy_url)
    adapter = BoundedCrawlAdapter(proxy=proxy, storage=storage)

    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        repo = CrawlRepository(connection)
        scope = repo.load_active_approval(source_id)
        if scope is None:
            connection.rollback()
            return {
                **state,
                "status": "crawl_failed",
                "detail": "missing_or_expired_source_approval",
            }
        crawl_version = repo.next_crawl_version(source_id)
        crawl_run_id = repo.create_crawl_run(
            source_id=source_id,
            version_id=version_id,
            crawl_version=crawl_version,
            policy_version=scope.policy_version,
            start_url=scope.start_url,
        )
        connection.commit()

    try:
        result = adapter.crawl(
            scope,
            source_id=source_id,
            crawl_version=crawl_version,
        )
    except (CrawlPolicyError, CrawlLimitExceeded) as exc:
        result_detail = exc.reason
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_worker")
            repo = CrawlRepository(connection)
            from smart_rag_core.ingestion.crawl.adapter import CrawlRunResult

            failed = CrawlRunResult(
                crawl_version=crawl_version,
                policy_version=scope.policy_version,
                start_url=scope.start_url,
                pages_fetched=0,
                wire_bytes_total=0,
                decoded_bytes_total=0,
                failure_reason=result_detail,
            )
            repo.persist_crawl_result(
                crawl_run_id=crawl_run_id,
                source_id=source_id,
                result=failed,
            )
            connection.commit()
        return {
            **state,
            "status": "crawl_failed",
            "crawl_run_id": str(crawl_run_id),
            "detail": result_detail,
        }

    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_worker")
        repo = CrawlRepository(connection)
        repo.persist_crawl_result(
            crawl_run_id=crawl_run_id,
            source_id=source_id,
            result=result,
        )
        if result.failure_reason or not result.snapshots:
            connection.commit()
            return {
                **state,
                "status": "crawl_failed",
                "crawl_run_id": str(crawl_run_id),
                "pages_fetched": result.pages_fetched,
                "detail": result.failure_reason or "no_snapshots",
            }
        version_id = UUID(state["version_id"]) if state["version_id"] else None
        document_id = None
        document_title = "website"
        if version_id is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.title
                    FROM app.document_versions AS dv
                    JOIN app.documents AS d ON d.id = dv.document_id
                    WHERE dv.id = %s
                    """,
                    (version_id,),
                )
                meta = cursor.fetchone()
                if meta is not None:
                    document_id = UUID(str(meta[0]))
                    document_title = str(meta[1])
        if document_id is None or version_id is None:
            connection.rollback()
            return {
                **state,
                "status": "crawl_failed",
                "crawl_run_id": str(crawl_run_id),
                "pages_fetched": result.pages_fetched,
                "detail": "missing document/version for hybrid_index enqueue",
            }
        snapshots = [
            {
                "storage_bucket": snapshot.storage_bucket,
                "storage_path": snapshot.storage_path,
                "content_hash": snapshot.content_hash,
                "canonical_url": snapshot.canonical_url,
            }
            for snapshot in result.snapshots
        ]
        scan_error = scan_crawl_snapshots_before_index(
            connection,
            configurable=configurable,
            document_id=document_id,
            version_id=version_id,
            snapshots=result.snapshots,
            declared_category="website",
        )
        if scan_error is not None:
            connection.commit()
            return {
                **state,
                "status": "crawl_failed",
                "crawl_run_id": str(crawl_run_id),
                "pages_fetched": result.pages_fetched,
                "detail": scan_error,
            }
        if configurable_lease_lost(config):
            connection.rollback()
            return {
                **state,
                "status": "lease_invalid",
                "detail": "lease lost",
            }
        enqueue_hybrid_index_job(
            connection,
            document_id=document_id,
            version_id=version_id,
            estimated_size_bytes=int(result.decoded_bytes_total),
            payload_ref={
                "crawl_run_id": str(crawl_run_id),
                "snapshots": snapshots,
                "filename": "website.html",
                "document_title": document_title,
                "media_type": "text/html",
                "content_class": state["content_class"],
                "graph_eligible": state["graph_eligible"],
                "attestation_policy_version": state["attestation_policy_version"],
                "review_approved": True,
                "declared_category": "website",
            },
        )
        connection.commit()

    return {
        **state,
        "status": "crawl_completed",
        "crawl_run_id": str(crawl_run_id),
        "pages_fetched": result.pages_fetched,
        "detail": "crawl completed",
    }


def route_after_crawl_lease(state: IngestionCrawlState) -> str:
    """Route invalid leases to graph end."""

    if state["status"] == "lease_invalid":
        return END
    return "execute_approved_crawl"


def route_after_crawl(state: IngestionCrawlState) -> str:
    """Terminate after crawl execution."""

    return END


def build_crawl_graph() -> IngestionCrawlGraph:
    """Construct crawl ``StateGraph`` (not yet compiled)."""

    builder: IngestionCrawlGraph = StateGraph(
        IngestionCrawlState,
        input_schema=IngestionCrawlState,
        output_schema=IngestionCrawlState,
    )
    builder.add_node("validate_crawl_lease", validate_crawl_lease)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("execute_approved_crawl", execute_approved_crawl)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "validate_crawl_lease")
    builder.add_conditional_edges("validate_crawl_lease", route_after_crawl_lease)
    builder.add_edge("execute_approved_crawl", END)
    return builder


def build_crawl_ingestion_graph(
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    interrupt_after: Sequence[str] | None = None,
) -> CompiledIngestionCrawlGraph:
    """Compile crawl graph.

    Args:
        checkpointer: Optional Postgres checkpointer used by the worker.
        interrupt_after: Test-only interrupt points.

    Returns:
        Compiled crawl graph.
    """

    compiled = compile_ingestion_graph(
        build_crawl_graph(),
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )
    return compiled  # pyright: ignore[reportReturnType]


def scan_crawl_snapshots_before_index(
    connection: psycopg.Connection,
    *,
    configurable: dict[str, object],
    document_id: UUID,
    version_id: UUID,
    snapshots: list[WebSnapshotRecord],
    declared_category: str,
) -> str | None:
    """Scan every crawl snapshot with ClamAV before ``hybrid_index`` enqueue.

    Reuses ``scan_object_bytes`` / ClamAV from the scan-promote path. Does not
    invent a second scanner and never records a fake clean result.

    Args:
        connection: Open ``app_worker`` connection that already persisted
            snapshots.
        configurable: Graph configurable with Storage and ClamAV settings.
        document_id: Canonical document id.
        version_id: Canonical version id.
        snapshots: Immutable snapshot records from the crawl run.
        declared_category: Category stored on scan events (``website``).

    Returns:
        ``None`` when every snapshot is current-clean. Otherwise an operator
        detail explaining missing/dirty scan.

    Side Effects:
        Transitions the version ``uploaded`` → ``scanning``, inserts
        append-only ``document_scan_events``, and calls ClamAV INSTREAM.
    """

    if not snapshots:
        return "no_snapshots"
    storage_url = configurable.get("storage_url")
    storage_secret = configurable.get("storage_admin_secret")
    clamav_host = configurable.get("clamav_host", "clamav")
    clamav_port_raw = configurable.get("clamav_port", 3310)
    clamav_port = int(clamav_port_raw) if isinstance(clamav_port_raw, int) else 3310
    if not isinstance(storage_url, str) or not isinstance(storage_secret, str):
        return "missing storage admin secret for snapshot scan"
    storage = StorageGateway(supabase_url=storage_url, admin_secret=storage_secret)
    clamav = ClamAvClient(host=str(clamav_host), port=clamav_port)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        status_row = cursor.fetchone()
    if status_row is None:
        return "version not found for snapshot scan"
    current_status = str(status_row[0])
    if current_status == "uploaded":
        try:
            connection.execute(
                """
                SELECT app.transition_document_version_status(
                  %s, 'uploaded'::app.document_status, 'scanning'::app.document_status
                )
                """,
                (version_id,),
            )
        except psycopg.Error as exc:
            return f"scanning_transition_failed:{exc}"[:400]
    elif current_status != "scanning":
        return f"unexpected status {current_status} before snapshot scan"
    scan_repo = ScanEventRepository(connection)
    hashes: list[str] = []
    for snapshot in snapshots:
        if configurable_lease_lost({"configurable": configurable}):
            return "lease lost"
        expected_bytes = int(snapshot.decoded_bytes)
        try:
            scan = scan_object_bytes(
                storage,
                clamav,
                ObjectScanInput(
                    bucket=snapshot.storage_bucket,
                    path=snapshot.storage_path,
                    expected_hash=snapshot.content_hash,
                    expected_bytes=expected_bytes,
                ),
            )
        except Exception as exc:
            return f"snapshot_scan_failed:{exc}"[:400]
        scan_repo.insert_scan_event(
            document_id=document_id,
            version_id=version_id,
            uploader_user_id=None,
            session_id=None,
            declared_category=declared_category,
            scan=scan,
        )
        if scan.result is not ScanResult.CLEAN:
            return (
                f"snapshot_scan_{scan.result.value}:"
                f"{scan.details.get('detail', scan.result.value)}"
            )[:400]
        hashes.append(snapshot.content_hash)
    if not scan_repo.has_current_clean_hashes(version_id, tuple(hashes)):
        return "missing_or_stale_snapshot_scan"
    return None
