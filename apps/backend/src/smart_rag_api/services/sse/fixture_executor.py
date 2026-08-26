"""Deterministic query-run executor for tests. No OpenAI."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext


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
