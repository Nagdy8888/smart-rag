"""Phase 3 approved website crawl graph nodes."""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict, cast
from uuid import UUID

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from smart_rag_core.gateways.crawl_proxy import CrawlProxyGateway
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.crawl.adapter import BoundedCrawlAdapter
from smart_rag_core.ingestion.crawl.exceptions import (
    CrawlLimitExceeded,
    CrawlPolicyError,
)
from smart_rag_core.jobs.exceptions import JobLeaseError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.repositories.crawl import CrawlRepository


class IngestionCrawlState(TypedDict):
    """Compact crawl graph state without raw page bytes."""

    job_id: str
    lease_token: str
    source_id: str | None
    version_id: str | None
    operation_key: str
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
    """Validate lease ownership before crawl side effects."""

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
    """Run bounded crawl through the restricted proxy and persist provenance."""

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
        connection.commit()

    if result.failure_reason or not result.snapshots:
        return {
            **state,
            "status": "crawl_failed",
            "crawl_run_id": str(crawl_run_id),
            "pages_fetched": result.pages_fetched,
            "detail": result.failure_reason or "no_snapshots",
        }
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


def build_crawl_ingestion_graph() -> CompiledIngestionCrawlGraph:
    """Compile crawl graph without checkpointer."""

    return build_crawl_graph().compile()  # pyright: ignore[reportUnknownMemberType]
