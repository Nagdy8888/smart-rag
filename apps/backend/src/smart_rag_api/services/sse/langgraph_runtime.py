"""Process bindings, memory store, checkpointer, and compiled query graph."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.settings import SharedSettings

LOGGER = logging.getLogger(__name__)


class StreamCancelFlag(Protocol):
    """Cooperative cancel handle used while opening ``astream``."""

    def is_set(self) -> bool:
        """Return whether cooperative cancel is set.

        Returns:
            True when deps should observe cancel.
        """
        ...


class LangGraphRuntimeFactory:
    """Process-reusable LangGraph bindings for one executor instance.

    Hybrid, store, and compiled graph open once. ``PostgresSaver.setup()``
    is never called.
    """

    def __init__(self) -> None:
        """Create empty caches. First use may open Postgres pools."""

        self._async_holder: Any = None
        self._store: Any = None
        self._bindings: Any = None
        self._compiled: Any = None
        self._compiled_checkpointer_id: int | None = None
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self.compile_count = 0

    @property
    def store(self) -> Any:
        """Return the opened compact memory store, if any.

        Returns:
            Store object or ``None``.
        """

        return self._store

    def process_bindings(self, settings: object) -> Any:
        """Return process-reusable Hybrid/gateway bindings.

        Args:
            settings: Backend settings used when lifespan state is absent.

        Returns:
            ``QueryGraphProcessBindings`` with non-null Hybrid and gateway.

        Raises:
            QueryGraphRuntimeError: When required adapters cannot be built.

        Side Effects:
            Caches process Hybrid/gateway bindings on this factory.
        """

        from smart_rag_api.services.query_graph_runtime import (
            build_query_process_bindings,
        )

        if self._bindings is not None:
            return self._bindings
        with self._sync_lock:
            if self._bindings is not None:
                return self._bindings
            self._bindings = build_query_process_bindings(
                settings=cast(SharedSettings | None, settings),
            )
            return self._bindings

    def bind_memory_store(self, settings: object) -> tuple[Any, Any]:
        """Open the compact memory store and checkpointer once per process.

        Args:
            settings: Backend settings with the checkpoint DSN.

        Returns:
            ``(store_get, store_put)`` callables, or ``(None, None)``.

        Side Effects:
            Opens a memory store on first use. The async checkpointer is
            opened separately.
        """

        resolved = getattr(settings, "resolved_checkpoint_dsn", None)
        dsn = resolved() if callable(resolved) else None
        if not isinstance(dsn, str) or not dsn:
            return None, None
        if self._store is None:
            with self._sync_lock:
                if self._store is None:
                    from smart_rag_agents.query.store import open_query_memory_store

                    self._store = open_query_memory_store(dsn)
        memory_store = self._store
        if memory_store is None:
            return None, None

        def _bind_put(
            namespace: tuple[str, str, str],
            key: str,
            payload: dict[str, object],
        ) -> None:
            """Write one compact store item.

            Args:
                namespace: Store namespace tuple.
                key: Item key.
                payload: Compact JSON mapping.
            """

            memory_store.put_compact(namespace, key, payload)

        return memory_store.get_compact, _bind_put

    async def ensure_async_checkpointer(self, settings: object) -> Any:
        """Open the compact async query checkpointer once per process.

        Args:
            settings: Backend settings with the checkpoint DSN.

        Returns:
            ``CompactAsyncPostgresSaver`` or ``None`` when no DSN is
            configured.

        Side Effects:
            Opens an async checkpointer pool on first use. Never calls
            ``setup()``.
        """

        if self._async_holder is not None:
            return self._async_holder.saver
        async with self._async_lock:
            if self._async_holder is not None:
                return self._async_holder.saver
            resolved = getattr(settings, "resolved_checkpoint_dsn", None)
            dsn = resolved() if callable(resolved) else None
            if not isinstance(dsn, str) or not dsn:
                return None
            from smart_rag_agents.query.checkpointer import (
                open_query_async_checkpointer,
            )

            self._async_holder = await open_query_async_checkpointer(dsn)
            return self._async_holder.saver

    def compiled_query_graph(self, checkpointer: object) -> object:
        """Compile the static topology once per factory and checkpointer.

        Args:
            checkpointer: Process async saver, or ``None``.

        Returns:
            Compiled query graph. Per-run deps are not captured.
        """

        marker = id(checkpointer) if checkpointer is not None else None
        if self._compiled is not None and self._compiled_checkpointer_id == marker:
            return self._compiled
        with self._sync_lock:
            if self._compiled is not None and self._compiled_checkpointer_id == marker:
                return self._compiled
            from smart_rag_agents.query.graph import compile_query_graph

            self._compiled = compile_query_graph(
                checkpointer=cast(BaseCheckpointSaver[str] | None, checkpointer),
            )
            self._compiled_checkpointer_id = marker
            self.compile_count += 1
            return self._compiled

    async def aclose(self) -> None:
        """Close cached checkpointer and memory-store pools.

        Side Effects:
            Drops compiled graph and adapter caches. ``setup()`` is never
            called. Exception text from pool close is not logged here.
        """

        holder = self._async_holder
        store = self._store
        self._async_holder = None
        self._store = None
        self._bindings = None
        self._compiled = None
        self._compiled_checkpointer_id = None
        if holder is not None:
            closer = getattr(holder, "close", None)
            if callable(closer):
                closed = closer()
                if inspect.isawaitable(closed):
                    await closed
        if store is not None:
            closer = getattr(store, "close", None)
            if callable(closer):
                closer()


async def open_langgraph_astream(
    *,
    settings: object,
    context: AuthorizedRuntimeContext,
    message: str,
    cancel_event: StreamCancelFlag,
    process_bindings: Callable[[object], Any],
    bind_memory_store: Callable[[object], Any],
    ensure_async_checkpointer: Callable[[object], Awaitable[Any]],
    compiled_query_graph: Callable[[object], object],
) -> tuple[Any, AsyncIterator[object], Any]:
    """Open the app_api connection, bind per-run deps, and start ``astream``.

    Args:
        settings: Loaded backend settings.
        context: Authorized run context.
        message: Untrusted user query.
        cancel_event: Cooperative cancel handle with ``is_set``.
        process_bindings: Executor or factory binding loader.
        bind_memory_store: Executor or factory store binder.
        ensure_async_checkpointer: Executor or factory checkpointer opener.
        compiled_query_graph: Executor or factory compile entry.

    Returns:
        ``(connection, stream_iter, deps)``.

    Side Effects:
        Binds run-local Web flags and ``QueryGraphDeps``, and opens one
        ``app_api`` connection on a worker thread; executor owns ``astream`` ``aclose``.
    """
    from smart_rag_agents.query.deps import QueryGraphContext, bind_query_run_deps
    from smart_rag_agents.query.graph import pending_query_state
    from smart_rag_agents.query.runtime.deps_factory import refresh_web_search_deps

    from smart_rag_api.services.query_graph_runtime import (
        build_query_graph_deps,
        open_run_app_api_connection_async,
    )
    from smart_rag_api.services.sse.stream_dispatch import production_astream_options

    bindings = process_bindings(settings)
    connection = await open_run_app_api_connection_async(bindings.supabase_dsn)
    store_binding = bind_memory_store(settings)
    if inspect.isawaitable(store_binding):
        store_get, store_put = await store_binding
    else:
        store_get, store_put = store_binding
    deps = build_query_graph_deps(
        bindings=bindings,
        connection=connection,
        cancel_check=cancel_event.is_set,
        store_get=store_get,
        store_put=store_put,
    )
    refresh_web_search_deps(deps, settings)
    LOGGER.info(
        "query graph deps bound web_enabled=%s web_configured=%s gateway=%s",
        int(bool(getattr(deps, "web_search_enabled", False))),
        int(bool(getattr(deps, "web_search_configured", False))),
        type(getattr(deps, "exa_search_gateway", None)).__name__,
        extra={"event": "query.graph.deps_bound"},
    )
    checkpointer = await ensure_async_checkpointer(settings)
    compiled = compiled_query_graph(checkpointer)
    state = pending_query_state(
        authorized_runtime=context.model_dump(mode="json"),
        user_query=message,
    )
    config: dict[str, object] = {
        "recursion_limit": context.recursion_limit,
        "configurable": {"thread_id": str(context.conversation_id)},
    }
    stream_iter = cast(
        AsyncIterator[object],
        compiled.astream(  # type: ignore[reportUnknownMemberType]
            state,
            cast(Any, config),
            context=QueryGraphContext(deps=deps),
            **production_astream_options(),
        ),
    )
    bind_query_run_deps(deps)
    return connection, stream_iter, deps
