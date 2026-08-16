"""Process-local SSE attach, heartbeat, cancel, and executor registry."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from fastapi.responses import StreamingResponse
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import (
    HEARTBEAT_INTERVAL_SECONDS,
    TERMINAL_SSE_EVENT_TYPES,
)
from smart_rag_core.sse.framing import format_sse_event
from smart_rag_core.sse.sanitize import sanitize_error_payload
from smart_rag_core.sse.store import PersistedRunEvent, RunEventStore

LOGGER = logging.getLogger(__name__)

SSE_RESPONSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

_POLL_SECONDS = 0.05
_NON_STARTABLE_STATUSES = frozenset(
    {"running", "completed", "cancelled", "partial", "failed"}
)


class QueryRunExecutor(Protocol):
    """Produces application SSE drafts. Heartbeat and schema are service-owned."""

    def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield ``(event_type, payload)`` until complete, cancelled, or failed.

        Args:
            context: Authorized runtime from admission.
            message: Untrusted user text for graph input.
            cancel_event: Set when POST ``/runs/{id}/cancel`` fires.

        Returns:
            Async iterator of allow-listed event type and extra=forbid payload.
        """

        raise NotImplementedError


class FixtureQueryRunExecutor:
    """Test executor: status, optional hold, optional completed. No OpenAI."""

    def __init__(
        self,
        *,
        hold_seconds: float | None = None,
        emit_completed: bool = True,
        extra_events: tuple[tuple[str, dict[str, object]], ...] = (),
    ) -> None:
        """Configure fixture behavior.

        Args:
            hold_seconds: Wait for cancel or timeout before completing.
            emit_completed: Yield a ``completed`` terminal when the hold ends.
            extra_events: Additional drafts after the initial status event.
        """

        self.hold_seconds = hold_seconds
        self.emit_completed = emit_completed
        self.extra_events = extra_events
        self.start_count = 0

    async def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Emit status, optional extras, then hold or complete.

        Args:
            context: Authorized context. Unused besides proving injection.
            message: Unused untrusted text.
            cancel_event: Stops a hold early without emitting completed.

        Yields:
            Fixture events. Never includes passage text.
        """

        del context, message
        self.start_count += 1
        yield ("status", {"stage": "admitted", "status": "running"})
        for event_type, payload in self.extra_events:
            yield (event_type, payload)
        if self.hold_seconds is not None:
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=self.hold_seconds)
            except TimeoutError:
                pass
            if cancel_event.is_set():
                return
        if self.emit_completed:
            yield ("completed", {})


class LangGraphQueryRunExecutor:
    """Production executor: ``graph.astream`` once per run, status per node."""

    async def execute(
        self,
        *,
        context: AuthorizedRuntimeContext,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Stream node completions as ``status`` events, then a terminal.

        Args:
            context: Server-derived ceilings and deadline.
            message: Untrusted user query.
            cancel_event: Stops iteration without restarting paid work later.

        Yields:
            Status events and at most one terminal. Retrieved source text is
            never copied into payloads.

        Raises:
            asyncio.CancelledError: When the wrapping task is cancelled.
        """

        if datetime.now(tz=UTC) >= context.deadline_at:
            yield ("deadline", {"route_family": context.route_family.value})
            yield ("partial", {"reason": "deadline_exhausted"})
            return

        from smart_rag_agents.query.graph import graph, pending_query_state

        state = pending_query_state(
            authorized_runtime=context.model_dump(mode="json"),
            user_query=message,
        )
        stream_name = "astream"
        stream_method = getattr(graph, stream_name)
        if not callable(stream_method):
            raise TypeError("graph_astream_missing")
        stream_iter = cast(
            AsyncIterator[object],
            stream_method(
                state,
                {"recursion_limit": context.recursion_limit},
                stream_mode="updates",
            ),
        )
        try:
            async for raw_chunk in stream_iter:
                if cancel_event.is_set():
                    return
                chunk: object = raw_chunk
                if not isinstance(chunk, dict):
                    continue
                updates = {
                    str(node_name): update
                    for node_name, update in cast(dict[object, object], chunk).items()
                }
                for node_name, update in updates.items():
                    status = "running"
                    update_map: dict[str, object] = {}
                    if isinstance(update, dict):
                        update_map = {
                            str(key): value
                            for key, value in cast(dict[object, object], update).items()
                        }
                        raw_status = update_map.get("status")
                        if isinstance(raw_status, str) and raw_status:
                            status = raw_status[:64]
                    yield (
                        "status",
                        {"stage": node_name[:64], "status": status},
                    )
                    if update_map and raw_status_is_partial(update_map):
                        yield (
                            "deadline",
                            {"route_family": context.route_family.value},
                        )
                        yield ("partial", {"reason": "deadline_exhausted"})
                        return
            if not cancel_event.is_set():
                yield ("completed", {})
        finally:
            close = getattr(stream_iter, "aclose", None)
            if callable(close):
                closed = close()
                if inspect.isawaitable(closed):
                    await closed


def raw_status_is_partial(update: dict[str, object]) -> bool:
    """Return whether a node update is a deadline/partial terminal.

    Args:
        update: Node state mapping.

    Returns:
        True when status is ``verified_partial`` or ``insufficient_evidence``.
    """

    raw_status = update.get("status")
    return raw_status in {"verified_partial", "insufficient_evidence"}


class LiveQueryRun:
    """In-process handle for one run's executor and heartbeat."""

    def __init__(self) -> None:
        """Create an idle handle."""

        self.cancel_event = asyncio.Event()
        self.started = False
        self.terminal = False
        self.executor_task: asyncio.Task[None] | None = None
        self.heartbeat_task: asyncio.Task[None] | None = None


class QueryRunRegistry:
    """Process-local live runs and pending graph inputs keyed by ``run_id``."""

    def __init__(self) -> None:
        """Create an empty registry."""

        self._live: dict[UUID, LiveQueryRun] = {}
        self._inputs: dict[UUID, str] = {}
        self._contexts: dict[UUID, AuthorizedRuntimeContext] = {}

    def remember_input(
        self,
        run_id: UUID,
        message: str,
        context: AuthorizedRuntimeContext | None = None,
    ) -> None:
        """Store the user message and admit context for a later first attach.

        Args:
            run_id: Admitted run.
            message: Untrusted user text.
            context: Authorized runtime used to start the graph once.
        """

        self._inputs[run_id] = message
        if context is not None:
            self._contexts[run_id] = context

    def take_input(self, run_id: UUID) -> str:
        """Return the remembered message or empty string.

        Args:
            run_id: Run id.

        Returns:
            Stored message. Empty when this process never saw the POST body.
        """

        return self._inputs.get(run_id, "")

    def take_context(self, run_id: UUID) -> AuthorizedRuntimeContext | None:
        """Return the remembered admit context when this process saw the POST.

        Args:
            run_id: Run id.

        Returns:
            Stored context, or None after a process restart.
        """

        return self._contexts.get(run_id)

    def has_input(self, run_id: UUID) -> bool:
        """Return whether this process still has the POST body.

        Args:
            run_id: Run id.

        Returns:
            True when ``remember_input`` ran in this process.
        """

        return run_id in self._inputs

    def get(self, run_id: UUID) -> LiveQueryRun | None:
        """Return the live handle when this process owns the executor.

        Args:
            run_id: Run id.

        Returns:
            Live handle or None.
        """

        return self._live.get(run_id)

    def get_or_create(self, run_id: UUID) -> LiveQueryRun:
        """Return the existing handle or create an idle one.

        Args:
            run_id: Run id.

        Returns:
            Live handle.
        """

        handle = self._live.get(run_id)
        if handle is None:
            handle = LiveQueryRun()
            self._live[run_id] = handle
        return handle

    def drop(self, run_id: UUID) -> None:
        """Forget a finished live handle. Inputs stay for no-op reconnects.

        Args:
            run_id: Run id.
        """

        self._live.pop(run_id, None)

    def request_cancel(self, run_id: UUID) -> None:
        """Signal the live executor to stop. No-op when this process has none.

        Args:
            run_id: Run id.
        """

        handle = self._live.get(run_id)
        if handle is not None:
            handle.cancel_event.set()


class SseStreamService:
    """Persist-then-flush SSE attach for POST fetch and GET resume."""

    def __init__(
        self,
        *,
        store: RunEventStore,
        registry: QueryRunRegistry,
        executor: QueryRunExecutor,
        sse_schema_version: str,
        heartbeat_interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        """Bind store, registry, and executor.

        Args:
            store: Memory or Postgres event store used by this service.
            registry: Process-local live-run table.
            executor: LangGraph production executor or a test fixture.
            sse_schema_version: Value for the first ``schema`` event.
            heartbeat_interval_seconds: Production default is 15.
        """

        self._store = store
        self._registry = registry
        self._executor = executor
        self._sse_schema_version = sse_schema_version
        self._heartbeat_interval_seconds = heartbeat_interval_seconds

    def remember_admitted(
        self,
        caller: CallerContext,
        context: AuthorizedRuntimeContext,
        *,
        message: str,
    ) -> None:
        """Register ownership and the POST body after a successful admit.

        Args:
            caller: Owner.
            context: Admission result.
            message: Untrusted user text for a later first graph start.
        """

        record = QueryRunRecord(
            run_id=context.run_id,
            conversation_id=context.conversation_id,
            creator_user_id=context.user_id,
            status=context.status,
            reservation_id=context.reservation_id,
            created_at=None,
        )
        self._store.register_run(caller=caller, record=record)
        self._registry.remember_input(context.run_id, message, context)

    def assert_readable(self, caller: CallerContext, *, run_id: UUID) -> QueryRunRecord:
        """Authorize resume before headers are sent.

        Args:
            caller: Owner.
            run_id: Run id.

        Returns:
            Authorized run record.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned conversation.
        """

        return self._store.get_authorized_run(caller, run_id=run_id)

    def notify_cancel(self, caller: CallerContext, *, run_id: UUID) -> None:
        """Stop the live generator and persist ``cancelled`` if needed.

        Missing store rows are ignored so packet 5 fake cancel services still
        work. Live executors are signalled first.

        Args:
            caller: Owner.
            run_id: Run to cancel.
        """

        self._registry.request_cancel(run_id)
        try:
            self._store.get_authorized_run(caller, run_id=run_id)
        except QueryAdmissionError:
            return
        self._append(caller, run_id, "cancelled", {})
        handle = self._registry.get(run_id)
        if handle is not None:
            handle.terminal = True
            self._cancel_tasks(handle)

    async def iter_frames(
        self,
        caller: CallerContext,
        *,
        run_id: UUID,
        after: int,
        context: AuthorizedRuntimeContext | None = None,
    ) -> AsyncIterator[str]:
        """Replay persisted events, attach once, and yield framed SSE.

        Reconnect never starts a second graph when status is already
        running/completed/cancelled/partial/failed or this process has a live
        executor.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive sequence cursor.
            context: Fresh admit context used to start the graph.

        Yields:
            SSE frames. Persistence happens before each yield.

        Raises:
            QueryAdmissionError: Missing, foreign, or tombstoned run.
        """

        self.assert_readable(caller, run_id=run_id)
        cursor = after
        async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
            cursor = sequence
            yield frame
            if terminal:
                return

        record = self.assert_readable(caller, run_id=run_id)
        live = self._registry.get(run_id)
        if live is None and record.status in _NON_STARTABLE_STATUSES:
            self._emit_worker_unavailable(caller, run_id)
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                yield frame
                if terminal:
                    return
            return

        if live is None and record.status == "pending":
            if context is None and not self._registry.has_input(run_id):
                self._emit_worker_unavailable(caller, run_id)
                async for frame, sequence, terminal in self._replay(
                    caller, run_id, cursor
                ):
                    cursor = sequence
                    yield frame
                    if terminal:
                        return
                return
            live = self._registry.get_or_create(run_id)
            self._start_once(caller, record, live, context)

        if live is not None and not live.started and record.status == "pending":
            self._start_once(caller, record, live, context)

        loop = asyncio.get_running_loop()
        last_heartbeat_at = loop.time()
        while True:
            emitted = False
            async for frame, sequence, terminal in self._replay(caller, run_id, cursor):
                cursor = sequence
                emitted = True
                yield frame
                if terminal:
                    self._registry.drop(run_id)
                    return
            handle = self._registry.get(run_id)
            if handle is None or handle.terminal:
                async for frame, sequence, terminal in self._replay(
                    caller, run_id, cursor
                ):
                    cursor = sequence
                    yield frame
                    if terminal:
                        self._registry.drop(run_id)
                        return
                if not emitted:
                    return
            now = loop.time()
            if (
                handle is not None
                and not handle.terminal
                and not handle.cancel_event.is_set()
                and now - last_heartbeat_at >= self._heartbeat_interval_seconds
            ):
                self._append(caller, run_id, "heartbeat", {})
                last_heartbeat_at = now
            await asyncio.sleep(_POLL_SECONDS)

    def _start_once(
        self,
        caller: CallerContext,
        record: QueryRunRecord,
        live: LiveQueryRun,
        context: AuthorizedRuntimeContext | None,
    ) -> None:
        """Start the executor at most once in this process.

        Heartbeats are persisted by the attach loop while a stream is open.

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

        Args:
            caller: Owner.
            record: Run row.
            live: Process handle.
            message: User text.
            context: Optional admit context; reconstructed from the record
                when missing (GET-after-202 on the same process).
        """

        runtime = context or self._registry.take_context(record.run_id)
        if runtime is None:
            self._emit_worker_unavailable(caller, record.run_id)
            live.terminal = True
            self._cancel_tasks(live)
            return
        try:
            async for event_type, payload in self._executor.execute(
                context=runtime,
                message=message,
                cancel_event=live.cancel_event,
            ):
                if live.cancel_event.is_set():
                    break
                self._append(caller, record.run_id, event_type, payload)
            if not self._has_terminal(caller, record.run_id):
                if live.cancel_event.is_set():
                    self._append(caller, record.run_id, "cancelled", {})
                else:
                    self._append(caller, record.run_id, "completed", {})
        except asyncio.CancelledError:
            if not self._has_terminal(caller, record.run_id):
                self._append(caller, record.run_id, "cancelled", {})
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
                self._append(
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
                self._append(caller, run_id, "heartbeat", {})
        except asyncio.CancelledError:
            return

    def _ensure_schema(self, caller: CallerContext, run_id: UUID) -> None:
        """Persist ``schema`` as sequence 1 when the log is empty.

        Args:
            caller: Owner.
            run_id: Run id.
        """

        existing = self._store.list_after(caller, run_id=run_id, after=0)
        if existing:
            return
        self._append(
            caller,
            run_id,
            "schema",
            {"sse_schema_version": self._sse_schema_version},
        )

    def _emit_worker_unavailable(self, caller: CallerContext, run_id: UUID) -> None:
        """Persist schema then a sanitized terminal when this process cannot run.

        Args:
            caller: Owner.
            run_id: Run id.
        """

        self._ensure_schema(caller, run_id)
        if not self._has_terminal(caller, run_id):
            self._append(caller, run_id, "error", {"code": "worker_unavailable"})

    def _append(
        self,
        caller: CallerContext,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent | None:
        """Persist one event. Invalid drafts become a sanitized error.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted row, or None when append is rejected after sanitizing.
        """

        if event_type == "heartbeat" and self._has_terminal(caller, run_id):
            return None
        try:
            return self._store.append(
                caller,
                run_id=run_id,
                event_type=event_type,
                payload=payload,
            )
        except ValueError:
            LOGGER.info(
                "rejected sse payload",
                extra={"event": "sse.payload_rejected", "sse_event_type": event_type},
            )
            if event_type == "error":
                return None
            try:
                return self._store.append(
                    caller,
                    run_id=run_id,
                    event_type="error",
                    payload={"code": "run_failed"},
                )
            except (QueryAdmissionError, ValueError):
                return None
        except QueryAdmissionError:
            return None

    def _has_terminal(self, caller: CallerContext, run_id: UUID) -> bool:
        """Return whether a terminal event is already persisted.

        Args:
            caller: Owner.
            run_id: Run id.

        Returns:
            True when a terminal event exists.
        """

        events = self._store.list_after(caller, run_id=run_id, after=0)
        return any(item.event_type in TERMINAL_SSE_EVENT_TYPES for item in events)

    async def _replay(
        self, caller: CallerContext, run_id: UUID, after: int
    ) -> AsyncIterator[tuple[str, int, bool]]:
        """Yield framed events after ``after``.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive cursor.

        Yields:
            Frame text, new cursor, and whether the event is terminal.
        """

        for event in self._store.list_after(caller, run_id=run_id, after=after):
            frame = format_sse_event(
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
            )
            terminal = event.event_type in TERMINAL_SSE_EVENT_TYPES
            yield frame, event.sequence, terminal

    def _cancel_tasks(self, live: LiveQueryRun) -> None:
        """Cancel heartbeat and executor tasks for a finished run.

        Args:
            live: Process handle.
        """

        for task in (live.heartbeat_task, live.executor_task):
            if task is not None and not task.done():
                task.cancel()


def wants_event_stream(accept: str | None) -> bool:
    """Return whether ``Accept`` asks for SSE.

    Args:
        accept: Accept header.

    Returns:
        True when ``text/event-stream`` is present.
    """

    if accept is None:
        return False
    return "text/event-stream" in accept.lower()


def resume_after_sequence(after: int, last_event_id: str | None) -> int:
    """Combine ``after`` with SSE ``Last-Event-ID``.

    Args:
        after: Query parameter. ``0`` means from the start unless Last-Event-ID
            is higher.
        last_event_id: Optional SSE reconnect header.

    Returns:
        Exclusive cursor. Invalid Last-Event-ID values are ignored.
    """

    header_value = 0
    if last_event_id is not None and last_event_id.strip().isdigit():
        header_value = int(last_event_id.strip())
    return max(after, header_value)


def sse_streaming_response(frames: AsyncIterator[str]) -> StreamingResponse:
    """Build a ``text/event-stream`` response with no-buffering headers.

    Args:
        frames: Persist-then-flush iterator.

    Returns:
        StreamingResponse whose headers win over middleware ``setdefault``.
    """

    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


def default_executor_factory() -> QueryRunExecutor:
    """Return the production LangGraph executor.

    Returns:
        LangGraph-backed executor. Import-safe until ``execute`` runs.
    """

    return LangGraphQueryRunExecutor()
