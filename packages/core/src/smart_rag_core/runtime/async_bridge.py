"""Run awaitables from synchronous query-graph nodes without nested asyncio.run.

LangGraph query nodes stay synchronous. Production SSE uses
``compiled.astream`` on a live event loop, so ``asyncio.run`` raises
``RuntimeError``. When no loop is running, ``asyncio.run`` is correct.
When a loop is already running, this module drives the coroutine on a
dedicated thread with its own loop so the caller can block without
touching the live loop.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import TypeVar, cast

T = TypeVar("T")


def run_coro_blocking(coro: object) -> object:
    """Await one coroutine from a synchronous caller.

    Args:
        coro: Awaitable returned by an async adapter, or a non-coroutine
            test-double result that is returned unchanged.

    Returns:
        The coroutine result, or ``coro`` when it is not a coroutine.

    Raises:
        BaseException: Propagates whatever the coroutine raises.

    Side Effects:
        When no event loop is running, uses ``asyncio.run``. When a loop
        is already running, starts one daemon thread with a private loop,
        runs the coroutine to completion, then closes that loop. The live
        loop is never nested.

    Example:
        ``lead_set = run_coro_blocking(retriever.retrieve_local(...))``
    """

    if not asyncio.iscoroutine(coro):
        return coro
    typed = cast(Coroutine[object, object, T], coro)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(typed)
    return _run_in_dedicated_thread(typed)


def _run_in_dedicated_thread(coro: Coroutine[object, object, T]) -> T:
    """Drive one coroutine on a private thread and loop.

    Args:
        coro: Coroutine created by the caller. It is awaited only on the
            worker thread's loop.

    Returns:
        Coroutine result.

    Raises:
        BaseException: Re-raised on the calling thread after the worker
            finishes.
    """

    box: dict[str, T] = {}
    error: dict[str, BaseException] = {}

    def _worker() -> None:
        """Run ``coro`` to completion on a new event loop.

        Side Effects:
            Creates, runs, and closes a private loop. Stores the result
            or exception in the enclosing dicts.
        """

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            box["value"] = loop.run_until_complete(coro)
        except BaseException as exc:
            error["exc"] = exc
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    worker = threading.Thread(
        target=_worker,
        name="smart-rag-async-bridge",
        daemon=True,
    )
    worker.start()
    worker.join()
    if "exc" in error:
        raise error["exc"]
    return box["value"]
