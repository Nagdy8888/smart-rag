"""Postgres SSE event-store session reuse and close."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.sse.store import (
    EVENT_STORE_LOCK_TIMEOUT_SQL,
    PostgresRunEventStore,
    _raise_store_error,
    sqlstate_of,
)


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
    monkeypatch.setattr("smart_rag_core.sse.store.psycopg.connect", _connect)
    store = PostgresRunEventStore("postgresql://hosted")

    with store._transaction():
        pass
    with store._transaction():
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
        _raise_store_error(_LockError("lock timeout"))
    assert lock_exc.value.reason == "lock_timeout"
    with pytest.raises(QueryAdmissionError) as cancel_exc:
        _raise_store_error(_CancelError("statement timeout"))
    assert cancel_exc.value.reason == "statement_timeout"
