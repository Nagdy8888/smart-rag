"""Unit tests for blocking coroutine bridge used by sync query nodes."""

from __future__ import annotations

import asyncio
import time

import pytest
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

        raw = run_coro_blocking(_value())
        if not isinstance(raw, int):
            raise TypeError("expected int")
        return raw

    assert asyncio.run(_outer()) == 7


def test_run_coro_blocking_never_waits_for_trace_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retrieval bridge completion is independent of LangSmith availability."""

    from smart_rag_core.runtime import async_bridge

    def _slow_flush(*, timeout_seconds: float) -> None:
        """Model an unavailable telemetry exporter.

        Args:
            timeout_seconds: Unused simulated drain bound.
        """

        del timeout_seconds
        time.sleep(0.5)

    monkeypatch.setattr(
        async_bridge,
        "_flush_langsmith_traces",
        _slow_flush,
        raising=False,
    )
    started = time.monotonic()
    result = run_coro_blocking(_value())
    elapsed = time.monotonic() - started
    assert result == 7
    assert elapsed < 0.3


def test_run_coro_blocking_passthrough_non_coroutine() -> None:
    """Sync test doubles are returned unchanged."""

    assert run_coro_blocking(12) == 12
