# L2 - Pooled event-store sessions with a transaction-scoped role

Read `00-rules-and-commands.md` first (especially **How to apply an edit**).
L1 must be merged into your branch first.

## Goal (why)

`PostgresRunEventStore` (one object per API process, in
`app.state.run_event_store`) has **one** database session behind **one**
lock. Every run in the process shares it. A replay read waits for another
run's append, a heartbeat waits for a replay, and so on. At about 254 ms
per transaction this is the main cause of the slow event spacing after L1.

This packet also fixes a rule break. Each transaction runs
`SET ROLE app_api` (session level) on the Supavisor **transaction** pooler
and then commits. `docs/architecture/05-database-connections.md` says
transaction pooling "must not carry session GUC identity".

Changes:

1. New small, thread-safe pool class `BoundedConnectionPool` in
   `packages/core/src/smart_rag_core/settings/postgres_pool.py`. It lends
   at most N connections, reuses idle ones, closes connections idle 60 s
   or more, and opens connections only through `connect_postgres` (so
   prepared statements stay disabled). It has no new dependency. L6 reuses
   the same class.
2. The event store uses that pool (max 4) instead of one session.
3. `EVENT_STORE_SESSION_SQL` becomes
   `SET LOCAL ROLE app_api; SET LOCAL lock_timeout TO '2s'`, so both
   settings end at commit.

Not changed: the RPC SQL, `lock_timeout`, "discard the session on any
error", "append is never replayed", "`list_after` retries once on a
transient connect failure".

## Files this packet edits

| # | File |
| - | ---- |
| 1 | `packages/core/src/smart_rag_core/settings/postgres_pool.py` (new) |
| 2 | `packages/core/src/smart_rag_core/sse/store.py` |
| 3 | `tests/unit/test_postgres_pool.py` (new) |
| 4 | `tests/unit/test_query_sse_event_store.py` |
| 5 | `tests/contract/test_sse_run_lock.py` |
| 6 | `docs/architecture/05-database-connections.md` |
| 7 | `docs/api/SSE.md` |
| 8 | `docs/evaluation/QUERY_LATENCY_REPAIR_EVIDENCE.md` (L2 row) |

## Edit 1 - new file `packages/core/src/smart_rag_core/settings/postgres_pool.py`

File: `packages/core/src/smart_rag_core/settings/postgres_pool.py`

Full contents:

```python
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
```

## Edit 2 - `packages/core/src/smart_rag_core/sse/store.py`

File: `packages/core/src/smart_rag_core/sse/store.py`

2a. Find (exactly once):

```python
from threading import Lock, RLock
```

Replace with:

```python
from threading import Lock
```

2b. Find (exactly once):

```python
from smart_rag_core.settings.postgres_connect import (
    connect_postgres,
    is_transient_connect_failure,
)
```

Replace with:

```python
from smart_rag_core.settings.postgres_connect import is_transient_connect_failure
from smart_rag_core.settings.postgres_pool import BoundedConnectionPool, PoolBusyError
```

2c. Find (exactly once):

```python
EVENT_STORE_SESSION_SQL = f"SET ROLE app_api; {EVENT_STORE_LOCK_TIMEOUT_SQL}"
"""One parameter-free round trip that selects the API role and bounds lock
waits for the transaction. Psycopg 3 sends parameter-free multi-statement
strings with the simple query protocol."""
EVENT_STORE_IDLE_SECONDS = 60.0
```

Replace with:

```python
EVENT_STORE_SESSION_SQL = f"SET LOCAL ROLE app_api; {EVENT_STORE_LOCK_TIMEOUT_SQL}"
"""One parameter-free round trip that selects the API role and bounds lock
waits for this transaction only. ``SET LOCAL`` ends at commit, so a pooled
server session never keeps ``app_api``. Psycopg 3 sends parameter-free
multi-statement strings with the simple query protocol."""
EVENT_STORE_IDLE_SECONDS = 60.0
EVENT_STORE_POOL_MAX_SIZE = 4
"""Most concurrent event-store transactions per API process. Counted inside
the FastAPI request/RPC transaction-pooler cap (10) in
``docs/architecture/05-database-connections.md``."""
EVENT_STORE_POOL_WAIT_SECONDS = 2.0
"""Longest wait for a pooled event-store session. Matches ``lock_timeout``."""
```

2d. Replace `__init__`, `_discard_connection`, `_session`, and
`_transaction` of `class PostgresRunEventStore` in one edit.

Find (exactly once):

```python
    def __init__(
        self,
        postgres_url: str,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL. No connection is opened here.
            monotonic_clock: Injected clock for idle-reuse tests.
        """

        self._postgres_url = postgres_url
        self._connection: psycopg.Connection | None = None
        self._connection_lock = RLock()
        self._last_used = 0.0
        self._monotonic_clock = monotonic_clock

    def _discard_connection(self) -> None:
        """Close and drop the reusable session. Caller holds the lock."""

        connection = self._connection
        self._connection = None
        self._last_used = 0.0
        if connection is None:
            return
        try:
            connection.close()
        except Exception:
            return

    def _session(self) -> psycopg.Connection:
        """Return a connection idle for less than 60 seconds.

        Returns:
            Open connection with prepares disabled.
        """

        connection = self._connection
        if connection is not None and not connection.closed:
            idle = self._monotonic_clock() - self._last_used
            if idle < EVENT_STORE_IDLE_SECONDS:
                return connection
            self._discard_connection()
        connection = connect_postgres(self._postgres_url)
        self._connection = connection
        self._last_used = self._monotonic_clock()
        return connection

    @contextmanager
    def _transaction(self) -> Generator[psycopg.Connection, None, None]:
        """Yield one serialized transaction on a reusable database session.

        Reusing the API session avoids a TLS and hosted-pooler handshake for
        every SSE frame. Automatic prepared statements remain disabled because
        the configured Supabase transaction pooler can switch server sessions.
        A session idle for 60 seconds or more is closed before the next yield.
        The lock prevents concurrent executor, heartbeat, and replay operations
        from sharing a Psycopg transaction. Each transaction runs one
        parameter-free statement that does ``SET ROLE app_api`` and sets
        ``lock_timeout`` to two seconds so a run-row lock wait fails closed
        instead of sitting until the login role's 120-second statement
        timeout. Autocommit stays off. Any operation error rolls back
        best-effort, discards the session, and re-raises. Append/terminal
        callers must not replay the write.

        Yields:
            Open connection with ``app_api`` selected for this transaction.

        Raises:
            psycopg.Error: Connection, role, RPC, commit, or rollback failure.
        """

        with self._connection_lock:
            connection = self._session()
            try:
                connection.execute(EVENT_STORE_SESSION_SQL)
                yield connection
                connection.commit()
                self._last_used = self._monotonic_clock()
            except BaseException:
                try:
                    connection.rollback()
                except Exception:
                    LOGGER.info(
                        "event store rollback failed",
                        extra={
                            "operation": "event_store_rollback",
                            "attempt": 1,
                            "reason": "rollback_failed",
                        },
                    )
                self._discard_connection()
                raise
```

Replace with:

```python
    def __init__(
        self,
        postgres_url: str,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Store the app_api DSN and configure the session pool.

        Args:
            postgres_url: Postgres URL. No connection is opened here.
            monotonic_clock: Injected clock for idle-reuse tests.
        """

        self._pool = BoundedConnectionPool(
            postgres_url,
            max_size=EVENT_STORE_POOL_MAX_SIZE,
            wait_seconds=EVENT_STORE_POOL_WAIT_SECONDS,
            idle_seconds=EVENT_STORE_IDLE_SECONDS,
            name="sse-event-store",
            monotonic_clock=monotonic_clock,
        )

    @contextmanager
    def _transaction(self) -> Generator[psycopg.Connection, None, None]:
        """Yield one transaction on a pooled database session.

        Up to ``EVENT_STORE_POOL_MAX_SIZE`` transactions run at once, so a
        replay never waits for another run's append. Reusing pooled sessions
        avoids a TLS and hosted-pooler handshake for every SSE frame; a
        session idle for 60 seconds or more is closed instead of reused.
        Automatic prepared statements stay disabled because the Supabase
        transaction pooler can switch server sessions. Each transaction
        first runs one parameter-free statement that does
        ``SET LOCAL ROLE app_api`` and sets ``lock_timeout`` to two seconds,
        so the role and the limit end with the transaction and a run-row
        lock wait fails closed instead of sitting until the login role's
        120-second statement timeout. Autocommit stays off. Any operation
        error rolls back best-effort, closes that session, and re-raises.
        Append/terminal callers must not replay the write.

        Yields:
            Open connection with ``app_api`` selected for this transaction.

        Raises:
            QueryAdmissionError: ``event_store_busy`` when no pooled session
                frees up within ``EVENT_STORE_POOL_WAIT_SECONDS``.
            psycopg.Error: Connection, role, RPC, commit, or rollback failure.
        """

        try:
            connection = self._pool.acquire()
        except PoolBusyError as exc:
            raise QueryAdmissionError("event_store_busy") from exc
        reusable = False
        try:
            connection.execute(EVENT_STORE_SESSION_SQL)
            yield connection
            connection.commit()
            reusable = True
        except BaseException:
            try:
                connection.rollback()
            except Exception:
                LOGGER.info(
                    "event store rollback failed",
                    extra={
                        "operation": "event_store_rollback",
                        "attempt": 1,
                        "reason": "rollback_failed",
                    },
                )
            raise
        finally:
            self._pool.release(connection, reusable=reusable)
```

2e. The `close` method of `PostgresRunEventStore`. Find (exactly once):

```python
    def close(self) -> None:
        """Close the reusable database session.

        Side Effects:
            Waits for an active store transaction, then closes its connection.
            Calling this method more than once is safe.
        """

        with self._connection_lock:
            self._discard_connection()
```

Replace with:

```python
    def close(self) -> None:
        """Close pooled database sessions.

        Side Effects:
            Closes idle sessions now; a session lent to an active
            transaction is closed when that transaction ends. Calling this
            method more than once is safe.
        """

        self._pool.close()
```

2f. Check: `rg -n "_connection_lock|_discard_connection|_session\(|connect_postgres|RLock" packages/core/src/smart_rag_core/sse/store.py`
must print nothing (when `rg` finds nothing it exits with code 1; that is
the expected result here). `Lock` (without R) is still used by
`MemoryRunEventStore`.

## Edit 3 - new file `tests/unit/test_postgres_pool.py`

File: `tests/unit/test_postgres_pool.py`

Full contents:

```python
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
```

## Edit 4 - `tests/unit/test_query_sse_event_store.py`

File: `tests/unit/test_query_sse_event_store.py`

4a. Find (exactly once):

```python
    assert "SET ROLE app_api" in EVENT_STORE_SESSION_SQL
```

Replace with:

```python
    assert "SET LOCAL ROLE app_api" in EVENT_STORE_SESSION_SQL
```

4b. Find (exactly once):

```python
    assert typed_attr(store, "_connection") is None
```

Replace with:

```python
    assert typed_attr(store, "_pool").idle_count() == 0
```

4c. Append to the end of the file:

```python
def test_postgres_event_store_parallel_transactions_do_not_serialize(
    monkeypatch: Any,
) -> None:
    """Two threads get two pooled sessions and run their RPCs at once."""

    import threading
    import time
    from uuid import uuid4

    from smart_rag_core.security.identity import CallerContext, UserRole

    connects = {"n": 0}
    counter_lock = threading.Lock()

    def _rows() -> list[object]:
        """Return no replay rows.

        Returns:
            Empty list.
        """

        return []

    def _connect(url: str, **kwargs: object) -> object:
        """Return a new fake connection whose replay RPC takes 0.2 s.

        Args:
            url: DSN.
            **kwargs: Driver kwargs.

        Returns:
            Fake connection.
        """

        del url, kwargs
        with counter_lock:
            connects["n"] += 1
        connection = SimpleNamespace(closed=False)

        def _execute(statement: str, *_args: object) -> Any:
            """Sleep during the replay RPC.

            Args:
                statement: SQL statement.
                *_args: Bound parameters.

            Returns:
                Cursor stand-in.
            """

            if "list_run_events_after" in statement:
                time.sleep(0.2)
            return SimpleNamespace(fetchall=_rows)

        connection.execute = _execute
        connection.commit = lambda: None
        connection.rollback = lambda: None
        connection.close = lambda: setattr(connection, "closed", True)
        return connection

    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    store = PostgresRunEventStore("postgresql://hosted")
    caller = CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )

    def _read() -> None:
        """Replay one run."""

        store.list_after(caller, run_id=uuid4(), after=0)

    started = time.monotonic()
    threads = [threading.Thread(target=_read) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.monotonic() - started
    store.close()
    assert connects["n"] == 2
    assert elapsed < 0.35


def test_postgres_event_store_busy_pool_maps_to_admission_error(
    monkeypatch: Any,
) -> None:
    """A full pool fails in the wait bound with ``event_store_busy``."""

    from uuid import uuid4

    from smart_rag_core.security.identity import CallerContext, UserRole

    monkeypatch.setattr(sse_store_mod, "EVENT_STORE_POOL_MAX_SIZE", 1)
    monkeypatch.setattr(sse_store_mod, "EVENT_STORE_POOL_WAIT_SECONDS", 0.05)
    connection = SimpleNamespace(closed=False)

    def _execute(statement: str, *_args: object) -> Any:
        """Accept any statement.

        Args:
            statement: SQL statement.
            *_args: Bound parameters.

        Returns:
            Cursor stand-in.
        """

        del statement
        return SimpleNamespace(fetchall=list, fetchone=lambda: None)

    connection.execute = _execute
    connection.commit = lambda: None
    connection.rollback = lambda: None
    connection.close = lambda: setattr(connection, "closed", True)

    def _connect(url: str, **kwargs: object) -> object:
        """Return the single fake connection.

        Args:
            url: DSN.
            **kwargs: Driver kwargs.

        Returns:
            Fake connection.
        """

        del url, kwargs
        return connection

    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    store = PostgresRunEventStore("postgresql://hosted")
    caller = CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )
    with typed_attr(store, "_transaction")():
        with pytest.raises(QueryAdmissionError) as busy:
            store.list_after(caller, run_id=uuid4(), after=0)
    store.close()
    assert busy.value.reason == "event_store_busy"
```

Do not change any other test in this file. The tests
`test_postgres_event_store_reuses_and_closes_session`,
`test_postgres_event_store_replaces_connection_after_61s_idle`,
`test_postgres_event_store_discards_on_error_without_append_replay`, and
`test_postgres_event_store_list_after_retries_before_rows` must pass with
only the two assertion changes in 4a and 4b.

## Edit 5 - `tests/contract/test_sse_run_lock.py`

File: `tests/contract/test_sse_run_lock.py`

Find (exactly once):

```python
def test_uncommitted_usage_blocks_append_until_lock_timeout(db_url: str) -> None:
```

This puts a new test above the existing one.

Replace with:

```python
def test_event_store_role_is_transaction_scoped(db_url: str) -> None:
    """``app_api`` ends with the store transaction on the reused session."""

    store = PostgresRunEventStore(db_url)
    try:
        with typed_attr(store, "_transaction")() as connection:
            inside_pid = connection.info.backend_pid
        pool = typed_attr(store, "_pool")
        reused = pool.acquire()
        try:
            assert reused.info.backend_pid == inside_pid
            role = reused.execute("SELECT current_user").fetchone()
            assert role is not None
            assert str(role[0]) != "app_api"
            reused.rollback()
        finally:
            pool.release(reused, reusable=True)
    finally:
        store.close()


def test_uncommitted_usage_blocks_append_until_lock_timeout(db_url: str) -> None:
```

## Edit 6 - `docs/architecture/05-database-connections.md`

File: `docs/architecture/05-database-connections.md`

6a. Find (exactly once):

```markdown
SSE `PostgresRunEventStore` reuses a session idle for less than 60
seconds, then closes/discards it. Any operation error rolls back
best-effort, discards the session, and re-raises. Read-only `list_after`
may retry once before any row is returned. Append and terminal writes
never auto-replay.
```

Replace with:

```markdown
SSE `PostgresRunEventStore` lends sessions from a
`BoundedConnectionPool` (`smart_rag_core.settings.postgres_pool`): at most
`EVENT_STORE_POOL_MAX_SIZE` = 4 per API process, counted inside the
FastAPI request/RPC cap of 10 above. A session idle for 60 seconds or
more is closed instead of reused. A caller that waits more than 2 seconds
for a free session gets `event_store_busy`. Each transaction runs
`SET LOCAL ROLE app_api; SET LOCAL lock_timeout TO '2s'`, so no pooled
server session keeps `app_api` after commit. Any operation error rolls
back best-effort, closes that session, and re-raises. Read-only
`list_after` may retry once before any row is returned. Append and
terminal writes never auto-replay.
```

6b. Find (exactly once):

```text
  sse["SSE event store\nidle less than 60s"] --> helper
```

Replace with:

```text
  sse["SSE event store pool\nmax 4, idle 60s, SET LOCAL ROLE"] --> helper
```

## Edit 7 - `docs/api/SSE.md`

File: `docs/api/SSE.md`

Find (exactly once):

```markdown
`PostgresRunEventStore` keeps autocommit off. Each transaction runs one
parameter-free statement, `SET ROLE app_api; SET LOCAL lock_timeout TO '2s'`,
so both settings share one round trip. That matches the intended `app_api`
GUC. Hosted login-role sessions do not always inherit role timeouts after
`SET ROLE`, so the store must set the limit itself. `app.append_run_event`
stays a separate parameterized statement.
```

Replace with:

```markdown
`PostgresRunEventStore` keeps autocommit off and lends sessions from a
pool of at most 4 per API process (see
[05-database-connections.md](../architecture/05-database-connections.md)).
Each transaction runs one parameter-free statement,
`SET LOCAL ROLE app_api; SET LOCAL lock_timeout TO '2s'`, so both settings
share one round trip and both end at commit. Hosted login-role sessions
do not always inherit role timeouts after `SET ROLE`, so the store must
set the limit itself. `app.append_run_event` stays a separate
parameterized statement. A caller that waits more than 2 seconds for a
free session gets `event_store_busy`, which the append path logs and
handles like `lock_timeout`.
```

Check the link path: `docs/api/SSE.md` to `docs/architecture/05-database-connections.md`
is `../architecture/05-database-connections.md`. The file must exist:
`Test-Path docs/architecture/05-database-connections.md` prints `True`.

## Commands (run all; each must exit 0)

```powershell
uv run python -m ruff format packages/core/src/smart_rag_core/settings/postgres_pool.py packages/core/src/smart_rag_core/sse/store.py tests/unit/test_postgres_pool.py tests/unit/test_query_sse_event_store.py tests/contract/test_sse_run_lock.py
uv run python -m ruff check --select I --fix packages/core/src/smart_rag_core/settings/postgres_pool.py packages/core/src/smart_rag_core/sse/store.py tests/unit/test_postgres_pool.py tests/unit/test_query_sse_event_store.py tests/contract/test_sse_run_lock.py
uv run python -m pytest tests/unit/test_postgres_pool.py tests/unit/test_query_sse_event_store.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_readiness.py
uv run python -m pytest tests/contract/test_sse_run_lock.py
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier format
uv run python scripts/check.py --tier docs
```

Expected (measured in a dry run on 2026-09-24 with L0 and L1 applied):
the first pytest line prints `44 passed`; the contract line prints
`3 skipped` when no local database is configured; the unit tier prints
`1629 passed, 4 skipped`; types prints `0 errors`. A higher passed count
is fine if the repo gained tests; the word `failed` must not appear.

`tests/contract/test_sse_run_lock.py` skips on your machine when no local
Supabase is running. That is acceptable only if the `contract` job in the
PR checks runs it. After pushing, open that job's log and confirm
`test_event_store_role_is_transaction_scoped PASSED` (or `passed` in the
summary line with the file name). If it was skipped in CI too, write
"role test skipped in CI" in the report; do not claim it passed.

## Live proof

1. Before numbers: the `L1-after` report.
2. Rebuild and run the image probe. It must print `L2 present`.
3. Single user: timing run `L2-after`, then compare with `L1-after`.
   Expected: `event_spacing_median_s` clearly lower, `wall_seconds`
   median not higher than `L1-after` beyond the noise band.
4. Three users at once (checks the concurrency fix). Make three subset
   files with:

   ```powershell
   uv run python scripts/eval_latency_report.py subset --gold .private-eval/fresh50-v1.json --ids f03,f14,f15,f16 --out .private-eval/latency-par-1.json
   uv run python scripts/eval_latency_report.py subset --gold .private-eval/fresh50-v1.json --ids f23,f24,f33,f39 --out .private-eval/latency-par-2.json
   uv run python scripts/eval_latency_report.py subset --gold .private-eval/fresh50-v1.json --ids f41,f46,f47,f49 --out .private-eval/latency-par-3.json
   ```

   Start three runner processes at the same time (use the runner command
   from `00-rules-and-commands.md`, one per subset file, each with its own
   `--out-dir .private-eval/runs/L2-par-N`), with `Start-Process` so they
   run in parallel. Wait for all three. Then run
   `eval_latency_report.py report` on each folder.
5. If the runner output shows HTTP 409 or 429 for parallel runs (admission
   limit), record "parallel run limited by admission" and skip the
   parallel numbers; the unit test
   `test_postgres_event_store_parallel_transactions_do_not_serialize` is
   then the only concurrency proof.
6. Stop and report if the parallel median `wall_seconds` is more than
   1.5 times the single-user `L2-after` median.

## Done when

- [ ] Edits 1 to 7 applied exactly; `git diff --stat` lists only the files
      in the table above.
- [ ] Edit 2f check prints nothing.
- [ ] 6 pool tests and 2 new event-store tests pass; all other tests pass.
- [ ] Unit, lint, types, format, docs tiers pass.
- [ ] CI contract job ran `test_event_store_role_is_transaction_scoped`
      (or the skip is recorded honestly).
- [ ] `L2-after` compare pasted; parallel result or admission limit recorded;
      L2 evidence row filled.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

```text
perf(sse): pooled event-store sessions with transaction-scoped role (L2)
```

## Do not

- Do not add `psycopg-pool` or any other dependency.
- Do not enable autocommit or pipeline mode (L4 owns pipeline).
- Do not change `lock_timeout`, the RPC SQL, or the retry rules.
- Do not raise `EVENT_STORE_POOL_MAX_SIZE` above 4 without updating the
  budget doc and asking the user.
