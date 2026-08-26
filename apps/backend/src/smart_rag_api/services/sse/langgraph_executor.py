"""LangGraph ``updates``-mode query executor."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext

from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_api.services.sse.answer_persistence import AnswerPersistenceMixin
from smart_rag_api.services.sse.chunks import QuerySseChunk
from smart_rag_api.services.sse.constants import (
    QUERY_SSE_DEADLINE_MESSAGE,
    QUERY_SSE_GENERIC_FAILURE,
)
from smart_rag_api.services.sse.executor_protocol import QueryRunExecutor
from smart_rag_api.services.sse.langgraph_runtime import LangGraphRuntimeFactory
from smart_rag_api.services.sse.stream_lifecycle import StreamLifecycleMixin


class LangGraphQueryRunExecutor(
    StreamLifecycleMixin,
    AnswerPersistenceMixin,
    QueryRunExecutor,
):
    """Drive one query run from the compiled LangGraph ``updates`` stream.

    Per-run ``QueryGraphDeps`` are created after compile and passed through
    ``QueryGraphContext``. The compiled object stays process-reusable.
    """

    def __init__(self, factory: LangGraphRuntimeFactory | None = None) -> None:
        """Create the executor and an empty termination summary.

        Args:
            factory: Shared runtime factory. When omitted, a private factory
                is created for this instance.
        """

        self._factory = factory if factory is not None else LangGraphRuntimeFactory()
        self._store = self._factory.store
        self.termination_summary: dict[str, object] = {
            "termination_reason": "unknown",
            "terminal_event_type": None,
            "stream_exhausted": False,
        }

    async def execute(
        self,
        context: AuthorizedRuntimeContext,
        *,
        question: str,
        mapper: QuerySseMapper,
    ) -> AsyncIterator[QuerySseChunk]:
        """Stream mapped chunks from LangGraph ``updates``.

        Args:
            context: Authorized run context.
            question: User question already admitted for this run.
            mapper: Per-run mapper that owns first-terminal-wins.

        Yields:
            Mapped ``QuerySseChunk`` values. Persist work after ``completed``
            or ``partial`` is never surfaced as ``error``.
        """

        from smart_rag_api.services.query_graph_runtime import QueryGraphRuntimeError
        from smart_rag_core.query_admission.exceptions import QueryAdmissionError

        from smart_rag_agents.query.deps import QueryGraphContext
        from smart_rag_agents.query.state import (
            QueryGraphState,
            QueryGraphStateInput,
        )

        self._set_termination(reason="unknown", stream_exhausted=False)
        compiled: Any | None = None
        stream_iter: AsyncIterator[object] | None = None
        try:
            from smart_rag_api.settings import get_settings

            settings = get_settings()
            bindings = self._factory.process_bindings(settings)
            store_get, store_put = self._factory.bind_memory_store(settings)
            self._store = self._factory.store
            checkpointer = await self._factory.ensure_async_checkpointer(settings)
            compiled = self._factory.compiled_query_graph(checkpointer=checkpointer)
            from smart_rag_api.services.query_graph_runtime import (
                build_query_graph_deps,
            )

            deps = build_query_graph_deps(
                settings=settings,
                bindings=bindings,
                context=context,
                question=question,
                store_get=store_get,
                store_put=store_put,
            )
            graph_input: QueryGraphStateInput | QueryGraphState = (
                QueryGraphStateInput(question=question)
            )
            stream_iter = compiled.astream(
                graph_input,
                {
                    "configurable": {
                        "thread_id": str(context.run_id),
                    }
                },
                stream_mode="updates",
                context=QueryGraphContext(deps=deps),
            )
            async for payload in stream_iter:
                for chunk in mapper.map_update(payload):
                    if chunk.event_type in {"completed", "partial", "error"}:
                        if chunk.event_type == "error":
                            self._set_termination(
                                reason="error",
                                terminal_event_type=chunk.event_type,
                            )
                        else:
                            self._set_termination(
                                reason="completed"
                                if chunk.event_type == "completed"
                                else "partial",
                                terminal_event_type=chunk.event_type,
                            )
                            self._commit_successful_terminal(
                                context,
                                mapper,
                                settings,
                                remaining_model_calls=deps.remaining_model_calls,
                                terminal_status=mapper.last_status,
                            )
                    if mapper.input_tokens is not None or mapper.output_tokens is not None:
                        self._record_stream_usage(
                            input_tokens=mapper.input_tokens,
                            output_tokens=mapper.output_tokens,
                        )
                    yield chunk
                    if chunk.event_type in {"completed", "partial", "error"}:
                        return
            self.termination_summary["stream_exhausted"] = True
            if mapper.input_tokens is not None or mapper.output_tokens is not None:
                self._record_stream_usage(
                    input_tokens=mapper.input_tokens,
                    output_tokens=mapper.output_tokens,
                )
            if mapper.saw_terminal:
                if mapper.terminal_event_type == "error":
                    self._set_termination(
                        reason="error",
                        terminal_event_type="error",
                        stream_exhausted=True,
                    )
                else:
                    self._set_termination(
                        reason="completed"
                        if mapper.terminal_event_type == "completed"
                        else "partial",
                        terminal_event_type=mapper.terminal_event_type,
                        stream_exhausted=True,
                    )
                    self._commit_successful_terminal(
                        context,
                        mapper,
                        settings,
                        remaining_model_calls=deps.remaining_model_calls,
                        terminal_status=mapper.last_status,
                    )
                return
            self._set_termination(
                reason="interrupted",
                terminal_event_type=None,
                stream_exhausted=True,
            )
            yield QuerySseChunk(
                event_type="error",
                seq=mapper.next_seq(),
                payload={"message": QUERY_SSE_GENERIC_FAILURE},
            )
        except QueryAdmissionError:
            self._set_termination(reason="error", terminal_event_type="error")
            yield QuerySseChunk(
                event_type="error",
                seq=mapper.next_seq(),
                payload={"message": QUERY_SSE_GENERIC_FAILURE},
            )
        except QueryGraphRuntimeError:
            self._set_termination(reason="error", terminal_event_type="error")
            yield QuerySseChunk(
                event_type="error",
                seq=mapper.next_seq(),
                payload={"message": QUERY_SSE_GENERIC_FAILURE},
            )
        except TimeoutError:
            self._set_termination(
                reason="deadline",
                terminal_event_type="error",
            )
            yield QuerySseChunk(
                event_type="error",
                seq=mapper.next_seq(),
                payload={"message": QUERY_SSE_DEADLINE_MESSAGE},
            )
        except asyncio.CancelledError:
            self._set_termination(
                reason="cancelled",
                terminal_event_type=None,
            )
            raise
        except Exception:
            self._set_termination(reason="error", terminal_event_type="error")
            yield QuerySseChunk(
                event_type="error",
                seq=mapper.next_seq(),
                payload={"message": QUERY_SSE_GENERIC_FAILURE},
            )
        finally:
            if compiled is not None and stream_iter is not None:
                if self.termination_summary.get("stream_exhausted") is not True:
                    await self._aclose_stream(stream_iter)
