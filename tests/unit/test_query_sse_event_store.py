"""Postgres SSE event-store session reuse and close."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.sse import store as sse_store_mod
from smart_rag_core.sse.store import (
    EVENT_STORE_LOCK_TIMEOUT_SQL,
    PostgresRunEventStore,
    sqlstate_of,
)

from tests.unit.typed_attrs import typed_attr


def test_postgres_event_store_reuses_and_closes_session(monkeypatch: Any) -> None:
    """Hosted SSE transactions reuse one connection and close it explicitly."""

    calls: list[str] = []
    connection = SimpleNamespace(closed=False)

    def _execute(statement: str) -> None:
        """Record one connection statement.

        Args:
            statement: SQL statement.
        """

        calls.append(statement)

    def _commit() -> None:
        """Record a successful transaction commit."""

        calls.append("COMMIT")

    def _rollback() -> None:
        """Record a transaction rollback."""

        calls.append("ROLLBACK")

    def _close() -> None:
        """Mark the fake connection closed."""

        connection.closed = True
        calls.append("CLOSE")

    def _connect(url: str, *, prepare_threshold: int | None) -> object:
        """Return the single fake connection.

        Args:
            url: Connection URL.
            prepare_threshold: Automatic statement preparation threshold.

        Returns:
            Fake reusable connection.
        """

        calls.append(f"CONNECT {url} PREPARE {prepare_threshold}")
        return connection

    connection.execute = _execute
    connection.commit = _commit
    connection.rollback = _rollback
    connection.close = _close
    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    store = PostgresRunEventStore("postgresql://hosted")

    with typed_attr(store, "_transaction")():
        pass
    with typed_attr(store, "_transaction")():
        pass
    store.close()

    assert calls.count("CONNECT postgresql://hosted PREPARE None") == 1
    assert calls.count("SET ROLE app_api") == 2
    assert calls.count(EVENT_STORE_LOCK_TIMEOUT_SQL) == 2
    assert calls.index("SET ROLE app_api") < calls.index(EVENT_STORE_LOCK_TIMEOUT_SQL)
    assert calls.count("COMMIT") == 2
    assert calls[-1] == "CLOSE"


def test_sqlstate_of_walks_cause_chain() -> None:
    """SQLSTATE is read from the driver cause, not the admission wrapper."""

    class _DriverError(Exception):
        """Stand-in for a Psycopg error with SQLSTATE."""

        sqlstate = "55P03"

    wrapped = RuntimeError("wrapper")
    wrapped.__cause__ = _DriverError("canceling statement due to lock timeout")
    assert sqlstate_of(wrapped) == "55P03"
    assert sqlstate_of(RuntimeError("plain")) is None


def test_raise_store_error_maps_lock_sqlstates() -> None:
    """Lock and statement timeouts become stable admission reasons."""

    class _LockError(Exception):
        """Driver error with lock SQLSTATE."""

        sqlstate = "55P03"

    class _CancelError(Exception):
        """Driver error with statement-timeout SQLSTATE."""

        sqlstate = "57014"

    with pytest.raises(QueryAdmissionError) as lock_exc:
        typed_attr(sse_store_mod, "_raise_store_error")(_LockError("lock timeout"))
    assert lock_exc.value.reason == "lock_timeout"
    with pytest.raises(QueryAdmissionError) as cancel_exc:
        typed_attr(sse_store_mod, "_raise_store_error")(
            _CancelError("statement timeout")
        )
    assert cancel_exc.value.reason == "statement_timeout"


class _Clock:
    """Injectable monotonic clock for idle-reuse tests."""

    def __init__(self) -> None:
        """Start at t=0."""

        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time.

        Returns:
            Seconds.
        """

        return self.now


def test_postgres_event_store_replaces_connection_after_61s_idle(
    monkeypatch: Any,
) -> None:
    """Idle sessions at or beyond 60 seconds are discarded."""

    calls: list[str] = []
    connection = SimpleNamespace(closed=False)

    def _execute(statement: str) -> None:
        """Record SQL.

        Args:
            statement: SQL statement.
        """

        calls.append(statement)

    def _commit() -> None:
        """Record commit."""

        calls.append("COMMIT")

    def _rollback() -> None:
        """Record rollback."""

        calls.append("ROLLBACK")

    def _close() -> None:
        """Mark closed."""

        connection.closed = True
        calls.append("CLOSE")

    def _connect(url: str, **kwargs: object) -> object:
        """Return the fake connection and mark it open.

        Args:
            url: DSN.
            **kwargs: Driver kwargs.

        Returns:
            Fake connection.
        """

        connection.closed = False
        calls.append(f"CONNECT {url} PREPARE {kwargs.get('prepare_threshold')}")
        return connection

    connection.execute = _execute
    connection.commit = _commit
    connection.rollback = _rollback
    connection.close = _close
    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    clock = _Clock()
    store = PostgresRunEventStore("postgresql://hosted", monotonic_clock=clock)
    with typed_attr(store, "_transaction")():
        pass
    clock.now = 61.0
    with typed_attr(store, "_transaction")():
        pass
    store.close()
    assert calls.count("CONNECT postgresql://hosted PREPARE None") == 2
    assert calls.count("CLOSE") == 2


def test_postgres_event_store_discards_on_error_without_append_replay(
    monkeypatch: Any,
) -> None:
    """Operation errors discard the session and never replay append."""

    from uuid import uuid4

    import psycopg
    from smart_rag_core.security.identity import CallerContext, UserRole

    calls: list[str] = []
    connect_count = {"n": 0}
    append_count = {"n": 0}
    connection = SimpleNamespace(closed=False)

    def _none() -> None:
        """Return no fetchone row."""

        return None

    def _empty_rows() -> list[object]:
        """Return no fetchall rows.

        Returns:
            Empty list.
        """

        return []

    class _Boom(psycopg.OperationalError):
        """Transient append failure."""

        @property
        def sqlstate(self) -> str:
            """Return class 08 SQLSTATE.

            Returns:
                ``08006``.
            """

            return "08006"

    def _execute(statement: str, *_args: object) -> Any:
        """Fail append_run_event once.

        Args:
            statement: SQL statement.
            *_args: Bound parameters.

        Returns:
            Cursor stand-in.

        Raises:
            _Boom: When appending.
        """

        calls.append(statement)
        if "append_run_event" in statement:
            append_count["n"] += 1
            raise _Boom()
        return SimpleNamespace(fetchone=_none, fetchall=_empty_rows)

    def _commit() -> None:
        """Record commit."""

        calls.append("COMMIT")

    def _rollback() -> None:
        """Record rollback."""

        calls.append("ROLLBACK")

    def _close() -> None:
        """Mark closed."""

        connection.closed = True
        calls.append("CLOSE")

    def _connect(url: str, **kwargs: object) -> object:
        """Count connects.

        Args:
            url: DSN.
            **kwargs: Driver kwargs.

        Returns:
            Fake connection.
        """

        connect_count["n"] += 1
        calls.append(f"CONNECT {url} PREPARE {kwargs.get('prepare_threshold')}")
        connection.closed = False
        return connection

    connection.execute = _execute
    connection.commit = _commit
    connection.rollback = _rollback
    connection.close = _close
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
    with pytest.raises(QueryAdmissionError):
        store.append(
            caller,
            run_id=uuid4(),
            event_type="schema",
            payload={"sse_schema_version": "1"},
        )
    assert append_count["n"] == 1
    assert connect_count["n"] == 1
    assert "ROLLBACK" in calls
    assert "CLOSE" in calls
    assert typed_attr(store, "_connection") is None


def test_postgres_event_store_list_after_retries_before_rows(
    monkeypatch: Any,
) -> None:
    """Read-only replay retries once when no row was returned."""

    from uuid import uuid4

    import psycopg
    from smart_rag_core.security.identity import CallerContext, UserRole

    list_attempts = {"n": 0}
    connection = SimpleNamespace(closed=False)

    def _none() -> None:
        """Return no fetchone row."""

        return None

    def _empty_rows() -> list[object]:
        """Return no fetchall rows.

        Returns:
            Empty list.
        """

        return []

    class _Boom(psycopg.OperationalError):
        """Transient list failure."""

        @property
        def sqlstate(self) -> str:
            """Return class 08 SQLSTATE.

            Returns:
                ``08006``.
            """

            return "08006"

    def _execute(statement: str, *_args: object) -> Any:
        """Fail the first list RPC.

        Args:
            statement: SQL statement.
            *_args: Bound parameters.

        Returns:
            Cursor stand-in.

        Raises:
            _Boom: First list_run_events_after call.
        """

        if "list_run_events_after" in statement:
            list_attempts["n"] += 1
            if list_attempts["n"] == 1:
                raise _Boom()
            return SimpleNamespace(fetchall=_empty_rows)
        return SimpleNamespace(fetchall=_empty_rows, fetchone=_none)

    connection.execute = _execute
    connection.commit = lambda: None
    connection.rollback = lambda: None
    connection.close = lambda: setattr(connection, "closed", True)

    def _connect(url: str, **kwargs: object) -> object:
        """Return the fake connection.

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
    events = store.list_after(caller, run_id=uuid4(), after=0)
    assert events == ()
    assert list_attempts["n"] == 2
