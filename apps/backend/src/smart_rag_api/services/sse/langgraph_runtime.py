"""Process bindings, memory store, checkpointer, and compiled query graph."""

from __future__ import annotations

from typing import Any


class LangGraphRuntimeFactory:
    """Lazy process-reusable LangGraph bindings for one executor instance.

    ``PostgresSaver.setup()``, ``AsyncPostgresSaver.setup()``, and
    ``PostgresStore.setup()`` are never called.
    """

    def __init__(self) -> None:
        """Create empty caches. First use may open Postgres pools."""

        self._async_holder: Any = None
        self._store: Any = None
        self._bindings: Any = None
        self._compiled: Any = None
        self._compiled_checkpointer_id: int | None = None
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
        """

        from smart_rag_api.services.query_graph_runtime import (
            build_query_process_bindings,
        )

        if self._bindings is not None:
            return self._bindings
        self._bindings = build_query_process_bindings(settings=settings)
        return self._bindings

    def bind_memory_store(self, settings: object) -> tuple[Any, Any]:
        """Open the compact memory store and checkpointer once per process.

        Args:
            settings: Backend settings with the checkpoint DSN.

        Returns:
            ``(store_get, store_put)`` callables, or ``(None, None)``.
        """

        resolved = getattr(settings, "resolved_checkpoint_dsn", None)
        dsn = resolved() if callable(resolved) else None
        if not isinstance(dsn, str) or not dsn:
            return None, None
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
        """

        if self._async_holder is not None:
            return self._async_holder.saver
        resolved = getattr(settings, "resolved_checkpoint_dsn", None)
        dsn = resolved() if callable(resolved) else None
        if not isinstance(dsn, str) or not dsn:
            return None
        from smart_rag_agents.query.checkpointer import open_query_async_checkpointer

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
        from smart_rag_agents.query.graph import compile_query_graph

        self._compiled = compile_query_graph(checkpointer=checkpointer)
        self._compiled_checkpointer_id = marker
        self.compile_count += 1
        return self._compiled
