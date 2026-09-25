"""Small bounded pool of reusable Postgres connections.

Used where one API process needs a few parallel transactions on the hosted
transaction pooler without paying a new TLS and pooler handshake (about
500 ms) for each one. Connections come from ``connect_postgres`` so
automatic prepared statements stay disabled.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from threading import BoundedSemaphore, Lock

import psycopg

from smart_rag_core.settings.postgres_connect import connect_postgres

LOGGER = logging.getLogger(__name__)


class PoolBusyError(Exception):
    """No pooled connection became free within the wait bound."""


class BoundedConnectionPool:
    """Lend at most ``max_size`` connections and reuse idle ones newest-first.

    The constructor opens nothing. A lent connection must come back through
    ``release`` with no open transaction; pass ``reusable=False`` after any
    error so the connection is closed instead of reused. ``close`` closes
    idle connections and marks lent ones to be closed on release. The pool
    stays usable after ``close``: a later ``acquire`` connects again.

    Every method may be called from any thread.
    """

    def __init__(
        self,
        conninfo: str,
        *,
        max_size: int,
        wait_seconds: float,
        idle_seconds: float,
        name: str,
        monotonic_clock: Callable[[], float] = time.monotonic,
        connect: Callable[[str], psycopg.Connection] = connect_postgres,
    ) -> None:
        """Configure the pool. No connection is opened here.

        Args:
            conninfo: Postgres DSN. Never logged.
            max_size: Most connections lent at the same time.
            wait_seconds: Longest ``acquire`` wait for a free slot.
            idle_seconds: Idle connections this old or older are closed
                instead of reused.
            name: Short pool name used in logs.
            monotonic_clock: Injected clock for idle tests.
            connect: Injected connect function for tests.

        Raises:
            ValueError: ``max_size`` is below 1.
        """

        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        self._conninfo = conninfo
        self._max_size = max_size
        self._wait_seconds = wait_seconds
        self._idle_seconds = idle_seconds
        self._name = name
        self._clock = monotonic_clock
        self._connect = connect
        self._slots = BoundedSemaphore(max_size)
        self._lock = Lock()
        self._idle: list[tuple[psycopg.Connection, float]] = []
        self._lent: dict[int, int] = {}
        self._generation = 0

    @property
    def max_size(self) -> int:
        """Return the configured lend limit.

        Returns:
            Most connections lent at the same time.
        """

        return self._max_size

    def idle_count(self) -> int:
        """Return how many connections wait for reuse.

        Returns:
            Idle connection count.
        """

        with self._lock:
            return len(self._idle)

    def acquire(self) -> psycopg.Connection:
        """Lend one connection, reusing the most recently returned one.

        Returns:
            Open connection with no open transaction.

        Raises:
            PoolBusyError: No slot became free within ``wait_seconds``.
            psycopg.Error: Connect failure. The slot is freed first.
            OSError: Network failure before the driver wraps it.
        """

        if not self._slots.acquire(timeout=self._wait_seconds):
            LOGGER.info(
                "postgres pool busy",
                extra={"event": "postgres_pool.busy", "pool": self._name},
            )
            raise PoolBusyError(self._name)
        try:
            connection = self._take_idle()
            if connection is None:
                connection = self._connect(self._conninfo)
            with self._lock:
                self._lent[id(connection)] = self._generation
            return connection
        except BaseException:
            self._slots.release()
            raise

    def release(self, connection: psycopg.Connection, *, reusable: bool) -> None:
        """Take a lent connection back.

        Args:
            connection: Connection returned by ``acquire``.
            reusable: True only when the last transaction committed or
                rolled back cleanly. False closes the connection.

        Raises:
            ValueError: More releases than acquires (programming error).
        """

        try:
            with self._lock:
                generation = self._lent.pop(id(connection), None)
                keep = (
                    reusable
                    and generation == self._generation
                    and not connection.closed
                )
                if keep:
                    self._idle.append((connection, self._clock()))
            if not keep:
                _close_quietly(connection)
        finally:
            self._slots.release()

    def close(self) -> None:
        """Close idle connections; lent ones are closed when released.

        Calling this more than once is safe. The pool can lend again later.
        """

        with self._lock:
            self._generation += 1
            idle = [item[0] for item in self._idle]
            self._idle = []
        for connection in idle:
            _close_quietly(connection)

    def _take_idle(self) -> psycopg.Connection | None:
        """Pop the newest fresh idle connection and close stale ones.

        Returns:
            Reusable connection, or None when a new one must be opened.
        """

        now = self._clock()
        stale: list[psycopg.Connection] = []
        chosen: psycopg.Connection | None = None
        with self._lock:
            fresh: list[tuple[psycopg.Connection, float]] = []
            for connection, returned_at in self._idle:
                if connection.closed or now - returned_at >= self._idle_seconds:
                    stale.append(connection)
                else:
                    fresh.append((connection, returned_at))
            if fresh:
                chosen = fresh.pop()[0]
            self._idle = fresh
        for connection in stale:
            _close_quietly(connection)
        return chosen


def _close_quietly(connection: psycopg.Connection) -> None:
    """Close ``connection`` and ignore close errors.

    Args:
        connection: Connection to close.
    """

    try:
        connection.close()
    except Exception:
        return
