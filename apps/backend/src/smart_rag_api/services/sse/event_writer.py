"""Per-run ordered background writer for SSE executor drafts.

LangGraph ``astream`` only advances when its consumer asks for the next
chunk, so awaiting one event-store transaction per draft inside that
consumer adds every write to graph time. ``RunEventWriter`` hands drafts to
one background task that persists them in submit order while the graph
keeps running.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES
from smart_rag_core.sse.store import PersistedRunEvent

LOGGER = logging.getLogger(__name__)

EVENT_WRITER_MAX_PENDING = 32
"""Most drafts queued ahead of persistence for one run. A full queue makes
``submit`` wait, which bounds memory and how far frames can lag the graph."""

AppendFn = Callable[[str, dict[str, object]], Awaitable[PersistedRunEvent | None]]
"""Persist one draft. Returns the row, or None when the append was skipped."""

ExecutorAppendFn = Callable[
    [CallerContext, UUID, str, dict[str, object]],
    Awaitable[PersistedRunEvent | None],
]
"""Shape of ``EventAppendMixin._append_async``."""

_Draft = tuple[str, dict[str, object], float]


def _elapsed_ms(started: float) -> float:
    """Return milliseconds since ``started`` on the monotonic clock.

    Args:
        started: A ``time.monotonic()`` value.

    Returns:
        Non-negative elapsed milliseconds, rounded to 0.1 ms.
    """

    return round(max(0.0, time.monotonic() - started) * 1000.0, 1)


class RunEventWriter:
    """Persist one run's SSE drafts in submit order on a single task.

    One consumer task takes drafts from a bounded FIFO queue and awaits
    ``append`` for each, so persisted order equals submit order. The
    executor awaits ``flush`` after a terminal draft, so work that must
    follow a durable terminal (``commit_successful_terminal``) still does.

    An exception raised by ``append`` stops persistence: drafts queued
    after it are skipped, and every later ``submit`` and ``flush``
    re-raises it. ``close`` never re-raises it, so cleanup paths can always
    call it. Use one writer per run, only from the event-loop thread that
    created it.
    """

    def __init__(
        self,
        append: AppendFn,
        *,
        run_id: UUID,
        max_pending: int = EVENT_WRITER_MAX_PENDING,
    ) -> None:
        """Configure the writer. No task starts until the first ``submit``.

        Args:
            append: Coroutine function that persists one draft.
            run_id: Run whose drafts this writer persists. Used in logs.
            max_pending: Queue bound. Must be at least 1.

        Raises:
            ValueError: ``max_pending`` is below 1.
        """

        if max_pending < 1:
            raise ValueError("max_pending must be at least 1")
        self._append = append
        self._run_id = run_id
        self._queue: asyncio.Queue[_Draft | None] = asyncio.Queue(maxsize=max_pending)
        self._task: asyncio.Task[None] | None = None
        self._failure: Exception | None = None
        self._closed = False
        self._append_ms: list[float] = []
        self._lag_ms_max = 0.0
        self._flush_ms_max = 0.0

    async def submit(self, event_type: str, payload: dict[str, object]) -> None:
        """Queue one draft to persist after every earlier draft.

        Args:
            event_type: Catalog event type.
            payload: Draft payload. Not copied; do not change it afterwards.

        Raises:
            RuntimeError: The writer is closed.
            Exception: The stored ``append`` failure, when one happened.

        Side Effects:
            Starts the consumer task on first use. Waits while the queue
            already holds ``max_pending`` drafts.
        """

        self._raise_failure()
        if self._closed:
            raise RuntimeError("event writer is closed")
        if self._task is None:
            self._task = asyncio.create_task(self._drain())
        await self._queue.put((event_type, payload, time.monotonic()))

    async def flush(self) -> None:
        """Wait until every submitted draft is persisted or skipped.

        Raises:
            Exception: The stored ``append`` failure, when one happened.
        """

        started = time.monotonic()
        await self._queue.join()
        self._flush_ms_max = max(self._flush_ms_max, _elapsed_ms(started))
        self._raise_failure()

    async def close(self) -> None:
        """Wait for queued drafts, stop the consumer, and log a summary once.

        Safe to call more than once and after a failure. Never re-raises the
        stored ``append`` failure.

        Side Effects:
            Logs one ``sse.writer_summary`` info record with counts and
            millisecond timings only.
        """

        if self._closed:
            return
        self._closed = True
        task = self._task
        if task is not None:
            await self._queue.join()
            await self._queue.put(None)
            await task
            self._task = None
        LOGGER.info(
            "sse writer summary run_id=%s events=%d append_ms_p50=%.1f "
            "append_ms_max=%.1f lag_ms_max=%.1f flush_ms_max=%.1f",
            self._run_id,
            len(self._append_ms),
            statistics.median(self._append_ms) if self._append_ms else 0.0,
            max(self._append_ms, default=0.0),
            self._lag_ms_max,
            self._flush_ms_max,
            extra={"event": "sse.writer_summary"},
        )

    def abort(self) -> None:
        """Stop the consumer without waiting; queued drafts are not written.

        For cleanup paths where ``close`` did not finish, for example when
        the executor task is cancelled a second time. No-op after ``close``.

        Side Effects:
            Marks the writer closed and cancels the consumer task.
        """

        self._closed = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()

    def _raise_failure(self) -> None:
        """Re-raise the stored ``append`` failure, if any.

        Raises:
            Exception: The first exception raised by ``append``.
        """

        if self._failure is not None:
            raise self._failure

    async def _drain(self) -> None:
        """Persist queued drafts in order until the stop marker arrives.

        Side Effects:
            Calls ``append`` once per draft while no failure is stored, and
            marks every item done so ``flush`` and ``close`` can return.
        """

        while True:
            item = await self._queue.get()
            try:
                if item is None:
                    return
                if self._failure is None:
                    await self._persist(*item)
            finally:
                self._queue.task_done()

    async def _persist(
        self, event_type: str, payload: dict[str, object], submitted: float
    ) -> None:
        """Persist one draft and record timings, or store the failure.

        Args:
            event_type: Catalog event type.
            payload: Draft payload.
            submitted: ``time.monotonic()`` when the draft was submitted.

        Side Effects:
            On an ``append`` exception, stores it and logs one
            ``sse.writer_stopped`` record with the number of skipped drafts.
        """

        started = time.monotonic()
        try:
            await self._append(event_type, payload)
        except Exception as exc:
            self._failure = exc
            LOGGER.info(
                "sse writer stopped run_id=%s skipped=%d",
                self._run_id,
                self._queue.qsize(),
                extra={"event": "sse.writer_stopped", "error_type": type(exc).__name__},
            )
            return
        self._append_ms.append(_elapsed_ms(started))
        self._lag_ms_max = max(self._lag_ms_max, _elapsed_ms(submitted))


def executor_draft_writer(
    append: ExecutorAppendFn,
    *,
    caller: CallerContext,
    run_id: UUID,
    cancel_event: asyncio.Event,
) -> RunEventWriter:
    """Build the writer for one executor run.

    After a cancel request, queued non-terminal drafts are skipped:
    ``notify_cancel`` has already persisted ``cancelled``, so a draft
    written now would land after the terminal event. Terminal drafts still
    go to ``append``, which keeps exactly one terminal.

    Args:
        append: ``_append_async`` of the SSE service.
        caller: Run owner.
        run_id: Run id.
        cancel_event: The live handle's cancel event.

    Returns:
        A writer whose consumer task starts on the first ``submit``.
    """

    async def _persist(
        event_type: str, payload: dict[str, object]
    ) -> PersistedRunEvent | None:
        """Persist one draft unless a cancel made it obsolete.

        Args:
            event_type: Catalog event type.
            payload: Draft payload.

        Returns:
            Persisted row, or None when skipped or rejected.
        """

        if cancel_event.is_set() and event_type not in TERMINAL_SSE_EVENT_TYPES:
            return None
        return await append(caller, run_id, event_type, payload)

    return RunEventWriter(_persist, run_id=run_id)
