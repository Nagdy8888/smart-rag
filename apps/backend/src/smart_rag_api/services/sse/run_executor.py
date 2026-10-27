"""Executor task for one admitted query run.

The orchestration mixin starts this task once. Drafts persist in yield
order, and a terminal event is durable before post-terminal work.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES
from smart_rag_core.sse.sanitize import sanitize_error_payload
from smart_rag_core.sse.store import PersistedRunEvent

from smart_rag_api.services.sse.chunks import token_counts_from_update
from smart_rag_api.services.sse.event_writer import executor_draft_writer
from smart_rag_api.services.sse.executors import QueryRunExecutor
from smart_rag_api.services.sse.registry import LiveQueryRun, QueryRunRegistry
from smart_rag_api.services.sse.run_summary import build_termination_payload

LOGGER = logging.getLogger(__name__)


class RunExecutorMixin:
    """Mixin: run the graph executor once and persist its drafts."""

    _registry: QueryRunRegistry
    _executor: QueryRunExecutor
    _postgres_url: str | None

    if TYPE_CHECKING:

        def _load_durable_start(
            self, caller: CallerContext, run_id: UUID
        ) -> tuple[str, AuthorizedRuntimeContext] | None:
            """Load durable start input. Provided by RunSettlementMixin."""

            ...

        def _emit_worker_unavailable(self, caller: CallerContext, run_id: UUID) -> None:
            """Persist worker_unavailable. Provided by RunSettlementMixin."""

            ...

        def _cancel_tasks(self, live: LiveQueryRun) -> None:
            """Cancel live tasks. Provided by ReplayCancelMixin."""

            ...

        def _has_terminal(self, caller: CallerContext, run_id: UUID) -> bool:
            """Return whether a terminal event exists. Provided by ReplayCancelMixin."""

            ...

        async def _append_async(
            self,
            caller: CallerContext,
            run_id: UUID,
            event_type: str,
            payload: dict[str, object],
        ) -> PersistedRunEvent | None:
            """Persist one catalog event off the loop. Provided by EventAppendMixin."""

            ...

    async def _run_executor(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        message: str,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Run the executor once and persist its drafts.

        Drafts go through one ``RunEventWriter`` that persists them in
        yield order while the graph keeps running. The executor waits for
        it after each terminal draft, at the end of the stream, and on the
        cancel and error paths, so a terminal is durable before
        post-terminal work. Queued non-terminal drafts are skipped after a
        cancel request. Store calls run on worker threads, and attach loops
        are woken on each append and when the executor ends.

        Args:
            caller: Owner.
            record: Run row.
            live: Process handle.
            message: User text.
            context: Optional admit context; reconstructed from the record
                when missing (GET-after-202 on the same process).
        """

        runtime = context or self._registry.take_context(record.run_id)
        if (runtime is None or not message) and self._postgres_url:
            loaded = await asyncio.to_thread(
                self._load_durable_start, caller, record.run_id
            )
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        if runtime is None:
            await asyncio.to_thread(
                self._emit_worker_unavailable, caller, record.run_id
            )
            live.terminal = True
            live.notify_appended()
            self._cancel_tasks(live)
            return
        writer = executor_draft_writer(
            self._append_async,
            caller=caller,
            run_id=record.run_id,
            cancel_event=live.cancel_event,
        )
        try:
            from smart_rag_core.observability.query_run_trace import (
                invoke_traced_query_run_sse,
            )
            from smart_rag_core.settings import (
                SettingsValidationError,
                load_backend_settings,
            )

            try:
                settings = load_backend_settings()
            except (SettingsValidationError, ValueError):
                settings = None

            async def _consume() -> dict[str, object]:
                """Drain the executor and persist drafts.

                Returns:
                    Termination summary plus assistant text and usage when
                    the stream emitted those catalog events.
                """

                assistant_parts: list[str] = []
                prompt_tokens: int | None = None
                completion_tokens: int | None = None
                usage_reporting: dict[str, object] | None = None
                async for event_type, payload in self._executor.execute(
                    context=runtime,
                    message=message,
                    cancel_event=live.cancel_event,
                ):
                    await writer.submit(event_type, payload)
                    if event_type in TERMINAL_SSE_EVENT_TYPES:
                        await writer.flush()
                    if event_type == "token_delta":
                        delta = payload.get("delta")
                        if isinstance(delta, str) and delta:
                            assistant_parts.append(delta)
                    elif event_type == "usage":
                        raw_reporting = payload.get("cost_reporting")
                        if isinstance(raw_reporting, dict):
                            usage_reporting = cast(dict[str, object], raw_reporting)
                        event_prompt, event_completion = token_counts_from_update(
                            payload
                        )
                        if event_prompt is not None:
                            prompt_tokens = event_prompt
                        if event_completion is not None:
                            completion_tokens = event_completion
                await writer.flush()
                await writer.close()
                if not await asyncio.to_thread(
                    self._has_terminal, caller, record.run_id
                ):
                    if live.cancel_event.is_set():
                        await self._append_async(caller, record.run_id, "cancelled", {})
                    else:
                        await self._append_async(
                            caller,
                            record.run_id,
                            "error",
                            {"code": "run_failed"},
                        )
                return build_termination_payload(
                    getattr(self._executor, "termination_summary", None),
                    cancelled=live.cancel_event.is_set(),
                    assistant_parts=assistant_parts,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    usage_reporting=usage_reporting,
                )

            if settings is None:
                await _consume()
            else:
                await invoke_traced_query_run_sse(
                    _consume,
                    settings=settings,
                    run_id=record.run_id,
                    user_id=runtime.user_id,
                    user_message=message,
                    requested_route=runtime.route_family.value,
                    effective_route=runtime.route_family.value,
                )
        except asyncio.CancelledError:
            await writer.close()
            if not await asyncio.to_thread(self._has_terminal, caller, record.run_id):
                await self._append_async(caller, record.run_id, "cancelled", {})
            raise
        except Exception as exc:
            LOGGER.info(
                "query executor failed",
                extra={
                    "event": "sse.executor_failed",
                    "error_type": type(exc).__name__,
                },
            )
            await writer.close()
            if not await asyncio.to_thread(self._has_terminal, caller, record.run_id):
                await self._append_async(
                    caller,
                    record.run_id,
                    "error",
                    sanitize_error_payload(exc),
                )
        finally:
            writer.abort()
            live.terminal = True
            live.notify_appended()
            heartbeat = live.heartbeat_task
            if heartbeat is not None and not heartbeat.done():
                heartbeat.cancel()
