"""LangGraph v2 ``updates``+``custom`` query executor."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext

from smart_rag_api.services.sse.answer_persistence import AnswerPersistenceMixin
from smart_rag_api.services.sse.langgraph_runtime import (
    LangGraphRuntimeFactory,
    open_langgraph_astream,
)
from smart_rag_api.services.sse.langgraph_stream_consume import (
    MappedStreamResult,
    iter_mapped_langgraph_updates,
)
from smart_rag_api.services.sse.stream_lifecycle import StreamLifecycleMixin

LOGGER = logging.getLogger(__name__)


class LangGraphQueryRunExecutor(StreamLifecycleMixin, AnswerPersistenceMixin):
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

    async def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Stream node starts, completions, and one verified terminal.

        Args:
            context: Server-derived ceilings and deadline.
            message: Untrusted user query.
            cancel_event: Stops iteration without restarting paid work later.

        Yields:
            Status events and at most one terminal. Retrieved source text is
            never copied into payloads. Summary or assistant persist after
            ``completed``/``partial`` cannot replace that terminal.

        Raises:
            asyncio.CancelledError: When the wrapping task is cancelled.
            ExternalFlowBlockedError: When tracing would export real company
                content without a verified subprocessor matrix.
        """

        from smart_rag_core.observability.governance_gate import (
            assert_langsmith_export_permitted,
        )
        from smart_rag_core.security.external_processing import ContentClass
        from smart_rag_core.settings import load_backend_settings

        settings = load_backend_settings()
        assert_langsmith_export_permitted(
            tracing_enabled=settings.langsmith_tracing,
            content_class=(
                ContentClass.SYNTHETIC
                if (
                    settings.mock_model_mode
                    or settings.allows_unsigned_local_live_providers()
                )
                else ContentClass.REAL_COMPANY
            ),
            provider_settings_verified=settings.subprocessor_matrix_verified,
            local_unsigned_waiver=settings.allows_unsigned_local_live_providers(),
        )
        self._set_termination(
            reason="unknown",
            terminal_event_type=None,
            stream_exhausted=False,
        )
        if datetime.now(tz=UTC) >= context.deadline_at:
            self._set_termination(reason="deadline", terminal_event_type="partial")
            yield ("deadline", {"route_family": context.route_family.value})
            yield ("partial", {"reason": "deadline_exhausted"})
            return

        from smart_rag_api.services.query_graph_runtime import QueryGraphRuntimeError

        connection = None
        connection_closed = False
        stream_iter: AsyncIterator[object] | None = None
        stream_exhausted = False
        stream_aclose_called = False
        last_prompt_tokens: int | None = None
        last_completion_tokens: int | None = None

        def _close_connection() -> None:
            """Close the app_api connection exactly once."""

            nonlocal connection_closed
            if connection is None or connection_closed:
                return
            connection_closed = True
            connection.close()

        try:
            connection, stream_iter, _deps = await open_langgraph_astream(
                settings=settings,
                context=context,
                message=message,
                cancel_event=cancel_event,
                process_bindings=self._process_bindings,
                bind_memory_store=self._bind_memory_store,
                ensure_async_checkpointer=self._ensure_async_checkpointer,
                compiled_query_graph=self._compiled_query_graph,
            )
            from smart_rag_api.services.query_sse_mapping import QuerySseMapper

            mapper = QuerySseMapper()
            LOGGER.info(
                "query sse stream started",
                extra={"event": "query.sse.started", "run_id": str(context.run_id)},
            )
            async for item in iter_mapped_langgraph_updates(
                stream_iter=stream_iter,
                mapper=mapper,
                context=context,
                settings=settings,
                cancel_event=cancel_event,
                connection=connection,
                commit_successful_terminal=self._commit_successful_terminal,
                set_termination=self._set_termination,
                last_remaining_calls=context.model_call_ceiling,
                last_status="running",
            ):
                if isinstance(item, MappedStreamResult):
                    stream_exhausted = item.stream_exhausted
                    last_prompt_tokens = item.last_prompt_tokens
                    last_completion_tokens = item.last_completion_tokens
                    if stream_exhausted:
                        self._set_termination(
                            reason=str(
                                self.termination_summary.get("termination_reason")
                            ),
                            terminal_event_type=(
                                str(self.termination_summary["terminal_event_type"])
                                if isinstance(
                                    self.termination_summary.get("terminal_event_type"),
                                    str,
                                )
                                else None
                            ),
                            stream_exhausted=True,
                        )
                    continue
                yield item
        except QueryGraphRuntimeError as exc:
            self._set_termination(reason="error", terminal_event_type="error")
            yield ("error", {"code": exc.reason})
        except asyncio.CancelledError:
            self._set_termination(
                reason="interrupted",
                terminal_event_type=str(
                    self.termination_summary.get("terminal_event_type")
                )
                if self.termination_summary.get("terminal_event_type")
                else "cancelled",
                stream_exhausted=stream_exhausted,
            )
            raise
        except GeneratorExit:
            self._set_termination(
                reason="interrupted",
                stream_exhausted=stream_exhausted,
            )
            raise
        except Exception:
            self._set_termination(reason="error", terminal_event_type="error")
            raise
        finally:
            self._record_stream_usage(
                input_tokens=last_prompt_tokens,
                output_tokens=last_completion_tokens,
            )
            _close_connection()
            if (
                stream_iter is not None
                and not stream_exhausted
                and not stream_aclose_called
            ):
                stream_aclose_called = True
                await self._aclose_stream(stream_iter)
