"""Admission and run pools reuse one Postgres handshake across Asks."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from smart_rag_api.services.api_postgres_pool import (
    ADMISSION_POOL_MAX_SIZE,
    admission_session,
    close_api_postgres_pools,
)
from smart_rag_api.services.query_graph_runtime import (
    open_run_app_api_connection,
    release_run_app_api_connection,
)
from smart_rag_api.services.query_runs import QueryRunService
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import CallerContext, UserRole

_DSN = "postgresql://pool.example/smart_rag"


class _FakeConnection:
    """Connection stand-in that records SQL and stays open until close."""

    def __init__(self) -> None:
        """Create an idle open fake."""
        self.closed = False
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str) -> None:
        """Record one statement.

        Args:
            sql: SQL text.
        """
        self.sql.append(sql)

    def commit(self) -> None:
        """Record one commit."""
        self.commits += 1

    def rollback(self) -> None:
        """Accept rollback."""

    def close(self) -> None:
        """Mark the fake closed."""
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_pools() -> object:
    """Drop process pools so tests do not share sessions.

    Yields:
        Nothing. Pools are closed again after the test.
    """
    close_api_postgres_pools()
    yield
    close_api_postgres_pools()


def _caller() -> CallerContext:
    """Return a server-derived member caller.

    Returns:
        Caller with a fixed user id.
    """
    return CallerContext(
        user_id="11111111-1111-4111-8111-111111111111",
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def test_submit_reuses_one_connection_for_admit_append_and_next_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two Asks open one session, and each Ask admits and inserts on it."""
    opened: list[_FakeConnection] = []
    admitted: list[object] = []
    appended: list[object] = []
    run_id = uuid4()

    def _connect(dsn: str) -> _FakeConnection:
        """Open one fake and record it.

        Args:
            dsn: Unused URL.

        Returns:
            Open fake connection.
        """
        del dsn
        connection = _FakeConnection()
        opened.append(connection)
        return connection

    def _admit(connection: object, **kwargs: object) -> SimpleNamespace:
        """Record the admit connection.

        Args:
            connection: Session under test.
            **kwargs: Unused admit arguments.

        Returns:
            Result whose context carries ``run_id``.
        """
        del kwargs
        admitted.append(connection)
        return SimpleNamespace(context=SimpleNamespace(run_id=run_id), reconnect=False)

    def _append(connection: object, **kwargs: object) -> None:
        """Record the insert connection.

        Args:
            connection: Session under test.
            **kwargs: Unused insert arguments.
        """
        del kwargs
        appended.append(connection)

    monkeypatch.setattr(
        "smart_rag_api.services.api_postgres_pool.connect_postgres",
        _connect,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_admission.check_auth_rate_limit",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_admission.admit_query_run",
        _admit,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_runs.append_query_message",
        _append,
    )
    service = QueryRunService(_DSN)
    for _ in range(2):
        _context, stream_path = service.submit_auto_message(
            _caller(),
            conversation_id=uuid4(),
            idempotency_key=uuid4(),
            message="What is the refund period?",
            requested_search_scope=RequestedSearchScope.AUTO,
        )
        assert stream_path == f"/runs/{run_id}/events"
    assert len(opened) == 1
    assert admitted == [opened[0], opened[0]]
    assert appended == [opened[0], opened[0]]
    assert opened[0].sql.count("SET LOCAL ROLE app_api") == 4
    assert opened[0].commits == 4
    assert opened[0].closed is False


def test_message_persist_failure_marks_the_run_on_the_same_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed insert does not open a second connection to fail the run."""
    opened: list[_FakeConnection] = []
    failed: list[object] = []

    def _connect(dsn: str) -> _FakeConnection:
        """Open one fake and record it.

        Args:
            dsn: Unused URL.

        Returns:
            Open fake connection.
        """
        del dsn
        connection = _FakeConnection()
        opened.append(connection)
        return connection

    monkeypatch.setattr(
        "smart_rag_api.services.api_postgres_pool.connect_postgres",
        _connect,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_admission.check_auth_rate_limit",
        lambda **kwargs: None,
    )
    def _admit(connection: object, **kwargs: object) -> SimpleNamespace:
        """Return a fake admitted run.

        Args:
            connection: Unused session.
            **kwargs: Unused admit arguments.

        Returns:
            Result with a new run id.
        """
        del connection, kwargs
        return SimpleNamespace(context=SimpleNamespace(run_id=uuid4()), reconnect=False)

    def _append(connection: object, **kwargs: object) -> None:
        """Fail the message insert.

        Args:
            connection: Unused session.
            **kwargs: Unused insert arguments.

        Raises:
            psycopg.OperationalError: Always.
        """
        del connection, kwargs
        raise psycopg.OperationalError("persist failed")

    monkeypatch.setattr(
        "smart_rag_api.services.query_admission.admit_query_run",
        _admit,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_runs.append_query_message",
        _append,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_runs.fail_query_run",
        lambda connection, **kwargs: failed.append(connection),
    )
    service = QueryRunService(_DSN)
    with pytest.raises(QueryAdmissionError, match="message_persist_failed"):
        service.submit_auto_message(
            _caller(),
            conversation_id=uuid4(),
            idempotency_key=uuid4(),
            message="What is the refund period?",
            requested_search_scope=RequestedSearchScope.AUTO,
        )
    assert len(opened) == 1
    assert failed == [opened[0]]


def test_run_connection_is_reused_after_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second graph open reuses the connection the first run released."""
    opened: list[_FakeConnection] = []

    def _connect(dsn: str) -> _FakeConnection:
        """Open one fake and record it.

        Args:
            dsn: Unused URL.

        Returns:
            Open fake connection.
        """
        del dsn
        connection = _FakeConnection()
        opened.append(connection)
        return connection

    monkeypatch.setattr(
        "smart_rag_api.services.api_postgres_pool.connect_postgres",
        _connect,
    )
    first = open_run_app_api_connection(_DSN)
    release_run_app_api_connection(first)
    second = open_run_app_api_connection(_DSN)
    release_run_app_api_connection(second)
    assert opened == [first]
    assert second is first
    assert first.sql == ["SET ROLE app_api", "SET ROLE app_api"]
    assert first.closed is False


def test_busy_admission_pool_opens_a_direct_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full admission pool connects directly instead of failing the Ask."""
    opened: list[_FakeConnection] = []

    def _connect(dsn: str) -> _FakeConnection:
        """Open one fake and record it.

        Args:
            dsn: Unused URL.

        Returns:
            Open fake connection.
        """
        del dsn
        connection = _FakeConnection()
        opened.append(connection)
        return connection

    monkeypatch.setattr(
        "smart_rag_api.services.api_postgres_pool.connect_postgres",
        _connect,
    )
    managers = [admission_session(_DSN) for _ in range(ADMISSION_POOL_MAX_SIZE)]
    held = [manager.__enter__() for manager in managers]
    try:
        with admission_session(_DSN) as extra:
            assert extra is opened[-1]
            assert extra not in held
        assert extra.closed is True
        assert len(opened) == ADMISSION_POOL_MAX_SIZE + 1
        for connection in held:
            assert connection.closed is False
    finally:
        for manager in managers:
            manager.__exit__(None, None, None)
