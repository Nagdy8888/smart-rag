"""Terminal lookup, replay framing, cooperative cancel, and task cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES
from smart_rag_core.sse.framing import format_sse_event
from smart_rag_core.sse.store import RunEventStore

from smart_rag_api.services.sse.constants import CANCEL_GRACE_SECONDS
from smart_rag_api.services.sse.registry import LiveQueryRun


class ReplayCancelMixin:
    """Mixin: replay persisted frames and cancel live executor tasks."""

    _store: RunEventStore

    def _assert_stream_identity(self, caller: CallerContext) -> None:
        """Require the concrete service to provide live stream authorization."""
        raise NotImplementedError

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

        The store read runs on a worker thread so a slow database round trip
        cannot block the event loop.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive cursor.

        Yields:
            Frame text, new cursor, and whether the event is terminal.
        """

        await asyncio.to_thread(self._assert_stream_identity, caller)
        events = await asyncio.to_thread(
            self._store.list_after, caller, run_id=run_id, after=after
        )
        for event in events:
            await asyncio.to_thread(self._assert_stream_identity, caller)
            frame = format_sse_event(
                sequence=event.sequence,
                event_type=event.event_type,
                payload=event.payload,
            )
            terminal = event.event_type in TERMINAL_SSE_EVENT_TYPES
            yield frame, event.sequence, terminal

    async def _cooperative_cancel(self, live: LiveQueryRun) -> None:
        """Give the executor a short cleanup window, then hard-cancel.

        Args:
            live: Process handle whose cancel event is already set.

        Side Effects:
            Cancels ``executor_task`` only when it is still running after
            ``CANCEL_GRACE_SECONDS``. Marks the handle terminal.
        """

        executor = live.executor_task
        if executor is None or executor.done():
            live.terminal = True
            return
        try:
            await asyncio.wait_for(
                asyncio.shield(executor), timeout=CANCEL_GRACE_SECONDS
            )
        except TimeoutError:
            if not executor.done():
                executor.cancel()
                try:
                    await executor
                except asyncio.CancelledError:
                    pass
        except asyncio.CancelledError:
            if not executor.done():
                try:
                    await executor
                except asyncio.CancelledError:
                    pass
        live.terminal = True

    def _cancel_tasks(self, live: LiveQueryRun) -> None:
        """Cancel heartbeat and executor tasks for a finished run.

        Args:
            live: Process handle.
        """

        for task in (live.heartbeat_task, live.executor_task):
            if task is not None and not task.done():
                task.cancel()
