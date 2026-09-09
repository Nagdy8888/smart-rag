"""Process Hybrid, checkpointer, and compiled-graph bindings for LangGraph SSE."""

from __future__ import annotations

from typing import Any

from smart_rag_api.services.sse.langgraph_runtime import LangGraphRuntimeFactory


class LangGraphBindingMixin:
    """Cache process Hybrid, memory store, checkpointer, and compiled graph."""

    _factory: LangGraphRuntimeFactory
    _bindings: Any
    _store: Any
    _compiled: Any
    compile_count: int

    def _process_bindings(self, settings: object) -> Any:
        """Return process-reusable Hybrid/gateway bindings.

        Args:
            settings: Backend settings used when lifespan state is absent.

        Returns:
            ``QueryGraphProcessBindings`` with non-null Hybrid and gateway.
        """

        if self._bindings is not None:
            return self._bindings
        self._bindings = self._factory.process_bindings(settings)
        return self._bindings

    def _bind_memory_store(self, settings: object) -> Any:
        """Open the compact memory store once per process.

        Args:
            settings: Backend settings with the checkpoint DSN.

        Returns:
            ``(store_get, store_put)`` callables, or ``(None, None)``.
        """

        result = self._factory.bind_memory_store(settings)
        self._store = self._factory.store
        return result

    async def _ensure_async_checkpointer(self, settings: object) -> Any:
        """Open the compact async query checkpointer once per process.

        Args:
            settings: Backend settings with the checkpoint DSN.

        Returns:
            ``CompactAsyncPostgresSaver`` or ``None`` when no DSN is
            configured.
        """

        return await self._factory.ensure_async_checkpointer(settings)

    def _compiled_query_graph(self, checkpointer: object) -> object:
        """Compile the static topology once per executor and checkpointer.

        Args:
            checkpointer: Process async saver, or ``None``.

        Returns:
            Compiled query graph. Per-run deps are not captured.
        """

        compiled = self._factory.compiled_query_graph(checkpointer)
        self._compiled = compiled
        self.compile_count = self._factory.compile_count
        return compiled

    async def warmup(self, settings: object) -> None:
        """Open process Hybrid, store, checkpointer, and compiled graph.

        Args:
            settings: Backend settings with checkpoint DSN and adapters.

        Side Effects:
            Caches factory bindings so the first Ask run does not open
            hosted Postgres pools under the Composite deadline.
            ``setup()`` is never called.
        """

        self._process_bindings(settings)
        self._bind_memory_store(settings)
        checkpointer = await self._ensure_async_checkpointer(settings)
        self._compiled_query_graph(checkpointer)

    async def aclose(self) -> None:
        """Close cached checkpointer and memory-store pools.

        Side Effects:
            Drops factory caches so a later ``execute`` reopens them.
        """

        await self._factory.aclose()
