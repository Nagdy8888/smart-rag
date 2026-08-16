"""Bounded process/thread offload and event-loop lag sampling.

Pure-Python slices whose measured p95 exceeds 10 ms must use the process
pool. Blocking I/O and C-extension work uses the thread pool. Callers
propagate ``asyncio`` cancellation; worker threads may finish after cancel
but the awaiter does not observe their result.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import ParamSpec, TypeVar

CPU_SLICE_BUDGET_MS = 10.0
_DEFAULT_CPU_WORKERS = 2
_DEFAULT_IO_WORKERS = 8

P = ParamSpec("P")
T = TypeVar("T")


class OffloadCancelledError(asyncio.CancelledError):
    """Raised when an offloaded call is cancelled by the event loop."""


@dataclass(frozen=True, slots=True)
class EventLoopLagSample:
    """One lag measurement.

    Attributes:
        lag_seconds: Observed delay beyond the requested sleep interval.
        interval_seconds: Requested sleep interval.
        p95_seconds: Rolling p95 of recorded lags including this sample.
    """

    lag_seconds: float
    interval_seconds: float
    p95_seconds: float


def cpu_slice_over_budget(elapsed_seconds: float) -> bool:
    """Return whether a CPU slice exceeded the 10 ms in-process budget.

    Args:
        elapsed_seconds: Measured wall time of one Python slice.

    Returns:
        True when the slice must move to the process pool.
    """

    return elapsed_seconds * 1000.0 > CPU_SLICE_BUDGET_MS


def _percentile(values: tuple[float, ...], percentile: float) -> float:
    """Return a nearest-rank percentile.

    Args:
        values: Sampled lag seconds.
        percentile: Percentile in ``(0, 100]``.

    Returns:
        Selected sample, or 0.0 when empty.
    """

    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1, max(0, int(round((percentile / 100.0) * len(ordered)) - 1))
    )
    return ordered[index]


async def sample_event_loop_lag(
    *,
    samples: int = 20,
    interval_seconds: float = 0.01,
) -> EventLoopLagSample:
    """Measure event-loop lag with short sleeps.

    Args:
        samples: Number of sleep intervals.
        interval_seconds: Requested sleep per sample.

    Returns:
        Last sample plus p95 lag across the window.

    Raises:
        OffloadCancelledError: If the calling task is cancelled.
        ValueError: If ``samples`` is less than 1.
    """

    if samples < 1:
        raise ValueError("lag_samples_invalid")
    loop = asyncio.get_running_loop()
    lags: list[float] = []
    last = 0.0
    for _ in range(samples):
        started = loop.time()
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError as exc:
            raise OffloadCancelledError("event_loop_lag_cancelled") from exc
        last = max(0.0, (loop.time() - started) - interval_seconds)
        lags.append(last)
    return EventLoopLagSample(
        lag_seconds=last,
        interval_seconds=interval_seconds,
        p95_seconds=_percentile(tuple(lags), 95.0),
    )


class OffloadExecutor:
    """Owns bounded pools. Constructed at process lifespan, not import.

    Side Effects:
        Creates thread and process pools. ``aclose`` shuts them down without
        waiting forever (``wait=False`` after cancel).
    """

    def __init__(
        self,
        *,
        cpu_workers: int = _DEFAULT_CPU_WORKERS,
        io_workers: int = _DEFAULT_IO_WORKERS,
    ) -> None:
        """Create idle pools.

        Args:
            cpu_workers: Process pool size.
            io_workers: Thread pool size.
        """

        self._cpu = ProcessPoolExecutor(max_workers=max(1, cpu_workers))
        self._io = ThreadPoolExecutor(max_workers=max(1, io_workers))
        self._closed = False

    async def run_cpu(
        self, func: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """Run a picklable CPU function in the process pool.

        Args:
            func: Module-level callable (Windows spawn requirement).
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Function result.

        Raises:
            OffloadCancelledError: If the awaiter is cancelled.
            RuntimeError: If the executor is closed.
        """

        return await self._await_pool(self._cpu, func, *args, **kwargs)

    async def run_io(
        self, func: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """Run blocking I/O in the thread pool.

        Args:
            func: Callable executed off the event loop.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Function result.

        Raises:
            OffloadCancelledError: If the awaiter is cancelled.
            RuntimeError: If the executor is closed.
        """

        return await self._await_pool(self._io, func, *args, **kwargs)

    async def _await_pool(
        self,
        pool: ProcessPoolExecutor | ThreadPoolExecutor,
        func: Callable[P, T],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Submit to ``pool`` and convert task cancel into OffloadCancelledError.

        Args:
            pool: Thread or process pool.
            func: Target callable.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Function result.

        Raises:
            OffloadCancelledError: On task cancellation.
            RuntimeError: If closed.
        """

        if self._closed:
            raise RuntimeError("offload_executor_closed")
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(pool, partial(func, *args, **kwargs))
        try:
            return await future
        except asyncio.CancelledError as exc:
            future.cancel()
            raise OffloadCancelledError("offload_cancelled") from exc

    def close(self) -> None:
        """Shut down pools. Does not block the event loop on worker finish.

        Side Effects:
            Sets ``_closed`` and requests executor shutdown.
        """

        if self._closed:
            return
        self._closed = True
        self._cpu.shutdown(wait=False, cancel_futures=True)
        self._io.shutdown(wait=False, cancel_futures=True)


def blocking_sleep_seconds(duration: float) -> float:
    """Module-level sleep used by offload tests (picklable on Windows).

    Args:
        duration: Sleep seconds.

    Returns:
        The duration slept.
    """

    time.sleep(duration)
    return duration
