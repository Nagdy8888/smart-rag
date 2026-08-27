"""Start-once executor and heartbeat task helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.sanitize import sanitize_error_payload
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore

from smart_rag_api.services.sse.chunks import (
    coerce_stream_token_count,
    token_counts_from_update,
)
from smart_rag_api.services.sse.executors import QueryRunExecutor
from smart_rag_api.services.sse.registry import LiveQueryRun, QueryRunRegistry

LOGGER = logging.getLogger(__name__)


class RunOrchestrationMixin:
    """Mixin: start the graph once and persist executor plus heartbeat drafts."""

    _store: RunEventStore
    _registry: QueryRunRegistry
    _executor: QueryRunExecutor
    _postgres_url: str | None
    _heartbeat_interval_seconds: float

    if TYPE_CHECKING:

        def _ensure_schema(self, caller: CallerContext, run_id: UUID) -> None:
            """Persist the first schema event. Provided by RunSettlementMixin."""

        def _load_durable_start(
            self, caller: CallerContext, run_id: UUID
        ) -> tuple[str, AuthorizedRuntimeContext] | None:
            """Load durable start input. Provided by RunSettlementMixin."""

        def _emit_worker_unavailable(self, caller: CallerContext, run_id: UUID) -> None:
            """Persist worker_unavailable. Provided by RunSettlementMixin."""

        def _cancel_tasks(self, live: LiveQueryRun) -> None:
            """Cancel live tasks. Provided by ReplayCancelMixin."""

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

    def _start_once(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Start the executor at most once in this process.

        Durable heartbeats are owned only by ``_run_heartbeat``.

        Args:
            caller: Owner.
            record: Current run row.
            live: Process handle.
            context: Fresh admit context when the POST is still in-flight.
        """

        if live.started:
            return
        live.started = True
        self._ensure_schema(caller, record.run_id)
        try:
            self._store.mark_running(caller, run_id=record.run_id)
        except QueryAdmissionError:
            LOGGER.info(
                "query run not marked running",
                extra={
                    "event": "sse.mark_running_skipped",
                    "run_id": str(record.run_id),
                },
            )
        message = self._registry.take_input(record.run_id)
        runtime = context or self._registry.take_context(record.run_id)
        if (not message or runtime is None) and self._postgres_url:
            loaded = self._load_durable_start(caller, record.run_id)
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        live.executor_task = asyncio.create_task(
            self._run_executor(caller, record, live, message, runtime)
        )
        live.heartbeat_task = asyncio.create_task(
            self._run_heartbeat(caller, record.run_id, live)
        )

    async def _run_executor(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        message: str,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Run the executor once and persist its drafts.

        Each catalog append is awaited on a worker thread so a run-row
        lock wait cannot freeze this event loop. Sequence order is the
        executor yield order.

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
            loaded = self._load_durable_start(caller, record.run_id)
            if loaded is not None:
                loaded_message, loaded_runtime = loaded
                if not message:
                    message = loaded_message
                if runtime is None:
                    runtime = loaded_runtime
        if runtime is None:
            self._emit_worker_unavailable(caller, record.run_id)
            live.terminal = True
            self._cancel_tasks(live)
            return
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
                async for event_type, payload in self._executor.execute(
                    context=runtime,
                    message=message,
                    cancel_event=live.cancel_event,
                ):
                    await self._append_async(caller, record.run_id, event_type, payload)
                    if event_type == "token_delta":
                        delta = payload.get("delta")
                        if isinstance(delta, str) and delta:
                            assistant_parts.append(delta)
                    elif event_type == "usage":
                        event_prompt, event_completion = token_counts_from_update(
                            payload
                        )
                        if event_prompt is not None:
                            prompt_tokens = event_prompt
                        if event_completion is not None:
                            completion_tokens = event_completion
                if not self._has_terminal(caller, record.run_id):
                    if live.cancel_event.is_set():
                        await self._append_async(caller, record.run_id, "cancelled", {})
                    else:
                        await self._append_async(
                            caller,
                            record.run_id,
                            "error",
                            {"code": "run_failed"},
                        )
                summary = getattr(self._executor, "termination_summary", None)
                payload: dict[str, object]
                if isinstance(summary, dict):
                    typed_summary = cast(dict[object, object], summary)
                    payload = {str(key): value for key, value in typed_summary.items()}
                else:
                    payload = {
                        "termination_reason": (
                            "cancelled" if live.cancel_event.is_set() else "unknown"
                        ),
                        "terminal_event_type": None,
                        "stream_exhausted": False,
                    }
                if assistant_parts:
                    payload["assistant_message"] = "".join(assistant_parts)
                if prompt_tokens is None:
                    prompt_tokens = coerce_stream_token_count(
                        payload.get("input_tokens")
                    )
                if prompt_tokens is None:
                    prompt_tokens = coerce_stream_token_count(
                        payload.get("prompt_tokens")
                    )
                if completion_tokens is None:
                    completion_tokens = coerce_stream_token_count(
                        payload.get("output_tokens")
                    )
                if completion_tokens is None:
                    completion_tokens = coerce_stream_token_count(
                        payload.get("completion_tokens")
                    )
                if prompt_tokens is not None:
                    payload["input_tokens"] = prompt_tokens
                if completion_tokens is not None:
                    payload["output_tokens"] = completion_tokens
                input_count = coerce_stream_token_count(payload.get("input_tokens"))
                output_count = coerce_stream_token_count(payload.get("output_tokens"))
                if input_count is not None or output_count is not None:
                    from smart_rag_core.observability.langsmith_tracing import (
                        estimate_traced_chat_cost_usd,
                    )

                    input_total = 0 if input_count is None else input_count
                    output_total = 0 if output_count is None else output_count
                    payload["input_tokens"] = input_total
                    payload["output_tokens"] = output_total
                    payload["total_tokens"] = input_total + output_total
                    payload["estimated_cost_usd"] = float(
                        estimate_traced_chat_cost_usd(
                            input_tokens=input_total,
                            output_tokens=output_total,
                        )
                    )
                return payload

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
            if not self._has_terminal(caller, record.run_id):
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
            if not self._has_terminal(caller, record.run_id):
                await self._append_async(
                    caller,
                    record.run_id,
                    "error",
                    sanitize_error_payload(exc),
                )
        finally:
            live.terminal = True
            heartbeat = live.heartbeat_task
            if heartbeat is not None and not heartbeat.done():
                heartbeat.cancel()

    async def _run_heartbeat(
        self, caller: CallerContext, run_id: UUID, live: LiveQueryRun
    ) -> None:
        """Persist a heartbeat every interval until the run is terminal.

        Appends run off the event loop. A lock wait cannot freeze
        ``astream`` or SSE polling. A failed heartbeat degrades to a
        skipped beat.

        Args:
            caller: Owner.
            run_id: Run id.
            live: Process handle.
        """

        try:
            while not live.terminal and not live.cancel_event.is_set():
                await asyncio.sleep(self._heartbeat_interval_seconds)
                if live.terminal or live.cancel_event.is_set():
                    break
                if self._has_terminal(caller, run_id):
                    break
                await self._append_async(caller, run_id, "heartbeat", {})
        except asyncio.CancelledError:
            return
