"""FastAPI wrapper for live SSE query-graph adapters.

Studio's module-level ``graph`` stays checkpointer-free and unbound. Process
Hybrid/gateway/table bindings live in ``smart_rag_agents.query.live_runtime``.
This module only discovers FastAPI ``app.state`` after lifespan and re-exports
the FastAPI-independent helpers.
"""

from __future__ import annotations

import asyncio
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
)
from smart_rag_agents.query.live_runtime import (
    build_query_graph_deps as _build_query_graph_deps,
)
from smart_rag_agents.query.live_runtime import (
    build_query_process_bindings as _build_query_process_bindings,
)
from smart_rag_core.settings import SharedSettings

from smart_rag_api.services.api_postgres_pool import (
    checkout_run_connection,
    release_run_connection,
)

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
    "open_run_app_api_connection_async",
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


def open_run_app_api_connection(supabase_dsn: str) -> psycopg.Connection:
    """Lend one warm ``app_api`` connection for counted model calls on this run.

    The first checkout in a process opens a connection. Later runs reuse it
    after :func:`release_run_app_api_connection` returns it idle, so they
    skip the pooler handshake. A busy pool opens a direct connection instead
    of waiting.

    Args:
        supabase_dsn: Canonical Postgres URL.

    Returns:
        Autocommit-off connection with ``SET ROLE app_api``. Caller must
        release it with :func:`release_run_app_api_connection`.

    Raises:
        QueryGraphRuntimeError: If the connection cannot be opened.

    Side Effects:
        May open a Postgres session with automatic prepares disabled.
    """
    connection: psycopg.Connection | None = None
    try:
        connection = checkout_run_connection(supabase_dsn)
        connection.execute("SET ROLE app_api")
    except (psycopg.Error, OSError) as exc:
        if connection is not None:
            release_run_app_api_connection(connection, reusable=False)
        raise QueryGraphRuntimeError("app_api_connection_unbound") from exc
    return connection


def release_run_app_api_connection(
    connection: object,
    *,
    reusable: bool | None = None,
) -> None:
    """Return a run connection to the pool, or close a stand-in.

    Args:
        connection: Connection from :func:`open_run_app_api_connection`, or
            a test stand-in that only implements ``close``.
        reusable: When omitted, reuse only an idle open connection.
            ``False`` closes it. Stand-ins that this module did not lend
            are always closed.

    Side Effects:
        May leave ``connection`` idle for the next run, or close it.
    """
    release_run_connection(connection, reusable=reusable)


async def open_run_app_api_connection_async(supabase_dsn: str) -> psycopg.Connection:
    """Open the run's ``app_api`` connection on a worker thread.

    The connect (TLS plus pooler handshake, about 0.5 s) must not block the
    SSE event loop. A warm pooled connection returns without that handshake.
    ``open_run_app_api_connection`` is looked up in this module at call time,
    so tests that patch it here still apply.

    Args:
        supabase_dsn: Canonical Postgres URL.

    Returns:
        Autocommit-off connection with ``SET ROLE app_api``. Caller must
        release it with :func:`release_run_app_api_connection`.

    Raises:
        QueryGraphRuntimeError: If the connection cannot be opened.
    """
    return await asyncio.to_thread(open_run_app_api_connection, supabase_dsn)
