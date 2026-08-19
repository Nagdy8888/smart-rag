"""Unit tests for the worker LightRAG event-loop reuse helper."""

from __future__ import annotations

import asyncio

from smart_rag_worker.graph_runner import run_lightrag_coroutine


async def _value() -> int:
    """Return a sentinel from an async function.

    Returns:
        Constant ``7``.
    """

    return 7


def test_run_lightrag_coroutine_reuses_open_loop() -> None:
    """Bind and job processing must not ``asyncio.run`` a second loop."""

    loop = asyncio.new_event_loop()
    try:
        first = run_lightrag_coroutine(_value(), loop=loop)
        second = run_lightrag_coroutine(_value(), loop=loop)
        assert (first, second) == (7, 7)
        assert loop.is_closed() is False
    finally:
        loop.close()


def test_run_lightrag_coroutine_without_loop_uses_asyncio_run() -> None:
    """Unconfigured workers still run a one-shot coroutine."""

    assert run_lightrag_coroutine(_value(), loop=None) == 7
