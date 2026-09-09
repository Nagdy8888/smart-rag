"""LangGraph v2 `updates`+`custom` query executor."""

from __future__ import annotations

from smart_rag_api.services.sse.langgraph_execute import LangGraphExecuteMixin
from smart_rag_api.services.sse.langgraph_runtime import LangGraphRuntimeFactory


class LangGraphQueryRunExecutor(LangGraphExecuteMixin):
    """Production executor: compiled query graph with optional checkpoints."""

    def __init__(self, factory: LangGraphRuntimeFactory | None = None) -> None:
        """Create an executor that opens checkpointer/store lazily.

        Args:
            factory: Shared runtime factory. When omitted, a private factory
                is created for this instance.

        Side Effects:
            None at construction. First ``execute`` may open a Postgres pool
            and construct process Hybrid/gateway bindings.
            ``PostgresSaver.setup()``, ``AsyncPostgresSaver.setup()``, and
            ``PostgresStore.setup()`` are never called.
        """

        self._factory = factory if factory is not None else LangGraphRuntimeFactory()
        self._async_holder = None
        self._store = None
        self._bindings = None
        self._compiled = None
        self._compiled_checkpointer_id: int | None = None
        self.compile_count = 0
        self.termination_summary: dict[str, object] = {
            "termination_reason": "unknown",
            "terminal_event_type": None,
            "stream_exhausted": False,
        }
