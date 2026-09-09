"""LangGraph query-run execute loop extracted from the executor owner."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext

from smart_rag_api.services.sse.answer_persistence import AnswerPersistenceMixin
from smart_rag_api.services.sse.langgraph_bindings import LangGraphBindingMixin
from smart_rag_api.services.sse.langgraph_runtime import open_langgraph_astream
from smart_rag_api.services.sse.langgraph_stream_consume import (
    MappedStreamResult,
    iter_mapped_langgraph_updates,
)
from smart_rag_api.services.sse.mapping.contracts import DEADLINE_EXHAUSTED_DETAIL
from smart_rag_api.services.sse.stream_lifecycle import StreamLifecycleMixin

LOGGER = logging.getLogger(__name__)


class LangGraphExecuteMixin(
    LangGraphBindingMixin,
    StreamLifecycleMixin,
    AnswerPersistenceMixin,
):
    """Mixin: stream node starts, completions, and one verified terminal."""

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
            ``completed``/``partial`` cannot replace that terminal. Verified
            assistant text is still persisted when a later catalog assertion
            fails so the next question cannot drop the live answer.

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
            for event in deadline_partial_events(context):
                yield event
            return

        from smart_rag_api.services.query_graph_runtime import QueryGraphRuntimeError
        from smart_rag_api.services.query_sse_mapping import QuerySseMapper

        connection = None
        connection_closed = False
        stream_iter: AsyncIterator[object] | None = None
        stream_exhausted = False
        stream_aclose_called = False
        last_prompt_tokens: int | None = None
        last_completion_tokens: int | None = None
        mapper: QuerySseMapper | None = None

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
            if datetime.now(tz=UTC) >= context.deadline_at:
                self._set_termination(reason="deadline", terminal_event_type="partial")
                for event in deadline_partial_events(context):
                    yield event
                return
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
            if mapper is not None and mapper.verified_text:
                self._persist_assistant_answer(context, mapper, settings)
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


def deadline_partial_events(
    context: AuthorizedRuntimeContext,
) -> list[tuple[str, dict[str, object]]]:
    """Return the catalog deadline diagnostic plus partial terminal.

    Args:
        context: Run whose family is copied onto the diagnostic event.

    Returns:
        ``deadline`` then ``partial`` with ``reason=deadline_exhausted``.
    """

    return [
        ("deadline", {"route_family": context.route_family.value}),
        ("partial", {"reason": DEADLINE_EXHAUSTED_DETAIL}),
    ]
