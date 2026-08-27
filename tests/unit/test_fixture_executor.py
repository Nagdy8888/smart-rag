"""Fixture executor start count, hold/cancel, extras, and optional terminal."""

from __future__ import annotations

import asyncio

from smart_rag_api.services.sse.executors import FixtureQueryRunExecutor
from smart_rag_api.services.sse.fixture_executor import (
    FixtureQueryRunExecutor as OwnerFixture,
)

from tests.support.query_sse import runtime


def test_fixture_executor_is_reexported_from_the_barrel() -> None:
    """Compatibility barrel exports the same fixture class."""

    assert FixtureQueryRunExecutor is OwnerFixture


def test_fixture_start_count_and_event_order() -> None:
    """One execute increments start_count and preserves extra-event order."""

    executor = FixtureQueryRunExecutor(
        extra_events=(("status", {"stage": "prepare", "status": "running"}),),
    )

    async def _collect() -> list[str]:
        """Drain fixture event types."""

        events: list[str] = []
        async for event_type, _payload in executor.execute(
            context=runtime(),
            message="unused",
            cancel_event=asyncio.Event(),
        ):
            events.append(event_type)
        return events

    assert asyncio.run(_collect()) == ["status", "status", "completed"]
    assert executor.start_count == 1


def test_fixture_hold_cancels_without_terminal() -> None:
    """A set cancel event during hold skips the optional completed event."""

    executor = FixtureQueryRunExecutor(hold_seconds=2.0, emit_completed=True)
    cancel = asyncio.Event()
    cancel.set()

    async def _collect() -> list[str]:
        """Drain fixture event types after an immediate cancel."""

        events: list[str] = []
        async for event_type, _payload in executor.execute(
            context=runtime(),
            message="unused",
            cancel_event=cancel,
        ):
            events.append(event_type)
        return events

    assert asyncio.run(_collect()) == ["status"]
    assert executor.start_count == 1


def test_fixture_optional_terminal_can_be_omitted() -> None:
    """emit_completed=False ends after status without a terminal."""

    executor = FixtureQueryRunExecutor(emit_completed=False)

    async def _collect() -> list[str]:
        """Drain fixture event types."""

        events: list[str] = []
        async for event_type, _payload in executor.execute(
            context=runtime(),
            message="unused",
            cancel_event=asyncio.Event(),
        ):
            events.append(event_type)
        return events

    assert asyncio.run(_collect()) == ["status"]
