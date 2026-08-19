"""Unit tests for blocking coroutine bridge used by sync query nodes."""

from __future__ import annotations

import asyncio

from smart_rag_core.runtime.async_bridge import run_coro_blocking


async def _value() -> int:
    """Return a sentinel from an async function.

    Returns:
        Constant ``7``.
    """

    return 7


def test_run_coro_blocking_without_running_loop() -> None:
    """No live loop uses asyncio.run."""

    assert run_coro_blocking(_value()) == 7


def test_run_coro_blocking_from_running_loop() -> None:
    """A live loop uses a dedicated thread instead of nested asyncio.run."""

    async def _outer() -> int:
        """Call the bridge while this loop is running.

        Returns:
            Inner coroutine result.
        """

        return int(run_coro_blocking(_value()))

    assert asyncio.run(_outer()) == 7


def test_run_coro_blocking_passthrough_non_coroutine() -> None:
    """Sync test doubles are returned unchanged."""

    assert run_coro_blocking(12) == 12
