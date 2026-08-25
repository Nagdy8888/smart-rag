"""FastAPI wrapper for live SSE query-graph adapters.

Studio's module-level ``graph`` stays checkpointer-free and unbound. Process
Hybrid/gateway/table bindings live in ``smart_rag_agents.query.live_runtime``.
This module only discovers FastAPI ``app.state`` after lifespan and re-exports
the FastAPI-independent helpers.
"""

from __future__ import annotations

from collections.abc import Callable

import psycopg
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.live_runtime import (
    DsnBm25Retriever,
    ProcessHybridRetriever,
    QueryGraphProcessBindings,
    QueryGraphRuntimeError,
    _context_loader,
    bind_table_executor,
    open_run_app_api_connection,
)
from smart_rag_agents.query.live_runtime import (
    build_query_graph_deps as _build_query_graph_deps,
)
from smart_rag_agents.query.live_runtime import (
    build_query_process_bindings as _build_query_process_bindings,
)
from smart_rag_core.settings import SharedSettings

__all__ = [
    "DsnBm25Retriever",
    "ProcessHybridRetriever",
    "QueryGraphProcessBindings",
    "QueryGraphRuntimeError",
    "_context_loader",
    "bind_table_executor",
    "build_query_graph_deps",
    "build_query_process_bindings",
    "open_run_app_api_connection",
]


def _lifespan_app_state() -> object | None:
    """Return process ``app.state`` after FastAPI lifespan when import-safe.

    Returns:
        ``app.state`` or None. Import is deferred to avoid a cycle with
        ``main`` which imports the SSE registry at module load.
    """

    try:
        from smart_rag_api.main import app as api_app
    except ImportError:
        return None
    return getattr(api_app, "state", None)


def build_query_process_bindings(
    *,
    settings: SharedSettings | None = None,
    app_state: object | None = None,
    supabase_dsn: str | None = None,
    model_gateway: object | None = None,
    lightrag_adapter: object | None = None,
    paradedb_url: str | None = None,
) -> QueryGraphProcessBindings:
    """Construct process-reusable Hybrid, gateway, table, and prompt bindings.

    Args:
        settings: Shared or backend settings. Loaded when omitted.
        app_state: Optional FastAPI ``app.state`` with lifespan adapters.
        supabase_dsn: Override canonical Postgres URL.
        model_gateway: Override gateway. Lifespan or ``create_model_gateway``
            is used when omitted.
        lightrag_adapter: Override graph retriever. Lifespan adapter is used
            when omitted. Missing adapter leaves graph unbound.
        paradedb_url: Override ``PARADEDB_URL``. Unset degrades BM25.

    Returns:
        Bindings with non-null Hybrid and model gateway.

    Raises:
        QueryGraphRuntimeError: When Hybrid or the gateway cannot be built.
    """

    return _build_query_process_bindings(
        settings=settings,
        app_state=app_state if app_state is not None else _lifespan_app_state(),
        supabase_dsn=supabase_dsn,
        model_gateway=model_gateway,
        lightrag_adapter=lightrag_adapter,
        paradedb_url=paradedb_url,
    )


def build_query_graph_deps(
    *,
    bindings: QueryGraphProcessBindings,
    connection: psycopg.Connection | None,
    cancel_check: Callable[[], bool] | None,
    store_get: Callable[[tuple[str, str, str], str], dict[str, object] | None]
    | None = None,
    store_put: Callable[[tuple[str, str, str], str, dict[str, object]], None]
    | None = None,
) -> QueryGraphDeps:
    """Assemble per-run ``QueryGraphDeps`` from process bindings.

    Args:
        bindings: Process Hybrid/gateway/table/prompts.
        connection: Per-run ``app_api`` connection for memory and counted
            model calls. Must not be shared across concurrent runs.
        cancel_check: Per-run cooperative cancellation probe.
        store_get: Optional compact memory reader.
        store_put: Optional compact memory writer.

    Returns:
        Deps with non-null ``hybrid_retriever`` and ``model_gateway``.

    Raises:
        QueryGraphRuntimeError: If required adapters are missing.
    """

    return _build_query_graph_deps(
        bindings=bindings,
        connection=connection,
        cancel_check=cancel_check,
        store_get=store_get,
        store_put=store_put,
    )
