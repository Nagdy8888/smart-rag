"""Bounded Postgres connection pool reuse, limits, and close."""

from __future__ import annotations

from typing import Any, cast

import pytest
from smart_rag_core.settings.postgres_pool import BoundedConnectionPool, PoolBusyError


class _FakeConnection:
    """Connection stand-in that records close."""

    def __init__(self, number: int) -> None:
        """Create an open fake.

        Args:
            number: Creation order, for assertions.
        """

        self.number = number
        self.closed = False

    def close(self) -> None:
        """Mark the fake closed."""

        self.closed = True


class _Connector:
    """Injected connect function that counts calls and can fail once."""

    def __init__(self, *, fail_first: bool = False) -> None:
        """Configure the connector.

        Args:
            fail_first: Raise ``OSError`` on the first call.
        """

        self.made: list[_FakeConnection] = []
        self.fail_first = fail_first
        self.calls = 0

    def __call__(self, conninfo: str) -> _FakeConnection:
        """Return a new fake connection.

        Args:
            conninfo: Unused DSN.

        Returns:
            New fake connection.

        Raises:
            OSError: On the first call when ``fail_first`` is set.
        """

        del conninfo
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise OSError("connect refused")
        connection = _FakeConnection(len(self.made) + 1)
        self.made.append(connection)
        return connection


class _Clock:
    """Injectable monotonic clock."""

    def __init__(self) -> None:
        """Start at t=0."""

        self.now = 0.0

    def __call__(self) -> float:
        """Return the fake time.

        Returns:
            Seconds.
        """

        return self.now


def _pool(
    connector: _Connector,
    *,
    max_size: int = 2,
    clock: _Clock | None = None,
) -> BoundedConnectionPool:
    """Build a pool around the fake connector.

    Args:
        connector: Fake connect function.
        max_size: Lend limit.
        clock: Optional fake clock.

    Returns:
        Pool under test.
    """

    return BoundedConnectionPool(
        "postgresql://fake",
        max_size=max_size,
        wait_seconds=0.05,
        idle_seconds=60.0,
        name="test",
        monotonic_clock=clock or _Clock(),
        connect=cast(Any, connector),
    )


def test_pool_reuses_newest_idle_connection() -> None:
    """Released connections are reused newest-first without reconnecting."""

    connector = _Connector()
    pool = _pool(connector)
    first = pool.acquire()
    second = pool.acquire()
    pool.release(first, reusable=True)
    pool.release(second, reusable=True)
    again = pool.acquire()
    assert again is second
    assert connector.calls == 2
    assert pool.idle_count() == 1


def test_pool_closes_stale_and_unreusable_connections() -> None:
    """Idle-expired and failed connections are closed, never lent again."""

    connector = _Connector()
    clock = _Clock()
    pool = _pool(connector, clock=clock)
    first = pool.acquire()
    pool.release(first, reusable=True)
    clock.now = 60.0
    second = pool.acquire()
    assert second is not first
    assert connector.made[0].closed is True
    pool.release(second, reusable=False)
    assert connector.made[1].closed is True
    assert pool.idle_count() == 0


def test_pool_limits_lent_connections() -> None:
    """A full pool raises ``PoolBusyError`` until a connection returns."""

    connector = _Connector()
    pool = _pool(connector, max_size=1)
    held = pool.acquire()
    with pytest.raises(PoolBusyError):
        pool.acquire()
    pool.release(held, reusable=True)
    assert pool.acquire() is held


def test_pool_frees_slot_when_connect_fails() -> None:
    """A failed connect does not leak the only slot."""

    connector = _Connector(fail_first=True)
    pool = _pool(connector, max_size=1)
    with pytest.raises(OSError, match="connect refused"):
        pool.acquire()
    connection = pool.acquire()
    assert connector.calls == 2
    pool.release(connection, reusable=True)


def test_pool_close_closes_idle_and_lent_on_release() -> None:
    """``close`` closes idle now, lent on release, and the pool still works."""

    connector = _Connector()
    pool = _pool(connector)
    idle = pool.acquire()
    lent = pool.acquire()
    pool.release(idle, reusable=True)
    pool.close()
    assert connector.made[0].closed is True
    assert connector.made[1].closed is False
    pool.release(lent, reusable=True)
    assert connector.made[1].closed is True
    assert pool.idle_count() == 0
    fresh = pool.acquire()
    assert fresh is connector.made[2]
    pool.close()


def test_pool_rejects_zero_size() -> None:
    """``max_size`` below one is a configuration error."""

    with pytest.raises(ValueError, match="max_size"):
        _pool(_Connector(), max_size=0)
