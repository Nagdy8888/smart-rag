"""Heartbeat loop for persist-then-flush query SSE runs."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.store import PersistedRunEvent

from smart_rag_api.services.sse.registry import LiveQueryRun


class RunHeartbeatMixin:
    """Mixin: persist catalog heartbeats until the run is terminal."""

    _heartbeat_interval_seconds: float

    if TYPE_CHECKING:

        async def _append_async(
            self,
            caller: CallerContext,
            run_id: UUID,
            event_type: str,
            payload: dict[str, object],
        ) -> PersistedRunEvent | None:
            """Persist one catalog event off the event loop."""

            ...

    async def _run_heartbeat(
        self, caller: CallerContext, run_id: UUID, live: LiveQueryRun
    ) -> None:
        """Persist a heartbeat every interval until the run is terminal.

        Appends run off the event loop, including the terminal check
        inside ``_append``. A store lock wait cannot freeze ``astream``
        or SSE polling. A failed heartbeat degrades to a skipped beat.

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
                await self._append_async(caller, run_id, "heartbeat", {})
        except asyncio.CancelledError:
            return
