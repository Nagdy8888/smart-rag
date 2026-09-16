"""Session/direct Postgres DSN guards never echo secrets."""

from __future__ import annotations

import psycopg
import pytest
from smart_rag_agents.ingestion.checkpointer import open_ingestion_checkpointer
from smart_rag_agents.query.store import open_query_memory_store
from smart_rag_core.settings.postgres_connect import connect_postgres
from smart_rag_core.settings.postgres_dsn import (
    TransactionPoolerDsnError,
    is_transaction_pooler_dsn,
    require_session_postgres_dsn,
)

_POOLER = "postgresql://unit:super-secret-pooler-password@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
_PGBOUNCER = "postgresql://unit:super-secret-pooler-password@127.0.0.1:5432/postgres?pgbouncer=true"
_SESSION = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
_SESSION_POOLER_HOST = (
    "postgresql://unit:unused@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
)


def test_transaction_pooler_port_and_pgbouncer_flag_are_detected() -> None:
    """Documented transaction-pooler signals are rejected; session 5432 is not."""

    assert is_transaction_pooler_dsn(_POOLER) is True
    assert is_transaction_pooler_dsn(_PGBOUNCER) is True
    assert is_transaction_pooler_dsn(_SESSION) is False
    assert is_transaction_pooler_dsn(_SESSION_POOLER_HOST) is False


def test_require_session_dsn_omits_url_from_error() -> None:
    """Fail-closed messages name the setting only."""

    with pytest.raises(TransactionPoolerDsnError) as exc_info:
        require_session_postgres_dsn(_POOLER, setting_name="LANGGRAPH_CHECKPOINT_URL")
    text = str(exc_info.value)
    assert "LANGGRAPH_CHECKPOINT_URL" in text
    assert "super-secret-pooler-password" not in text
    assert "pooler.supabase.com" not in text
    assert "postgresql://" not in text


def test_checkpointer_factory_rejects_pooler_before_connect() -> None:
    """Factories fail closed without opening a pooler connection."""

    with pytest.raises(TransactionPoolerDsnError) as exc_info:
        open_ingestion_checkpointer(_POOLER, max_size=1)
    assert "super-secret-pooler-password" not in str(exc_info.value)


def test_store_factory_rejects_pooler_before_connect() -> None:
    """Memory-store factory uses the same session/direct guard."""

    with pytest.raises(TransactionPoolerDsnError) as exc_info:
        open_query_memory_store(_PGBOUNCER, max_size=1)
    assert "super-secret-pooler-password" not in str(exc_info.value)


def test_connect_postgres_disables_automatic_prepares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query retrieve/persist must not name prepares on a transaction pooler."""

    captured: dict[str, object] = {}

    def _connect(dsn: str, **kwargs: object) -> object:
        """Record connect kwargs.

        Args:
            dsn: Caller DSN.
            **kwargs: Driver kwargs.

        Returns:
            Dummy connection.
        """

        del dsn
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    connect_postgres(_SESSION)
    assert captured["prepare_threshold"] is None


class _TransientConnectError(psycopg.OperationalError):
    """SQLSTATE class 08 connect failure."""

    @property
    def sqlstate(self) -> str:
        """Return a retryable connect SQLSTATE.

        Returns:
            Class 08 SQLSTATE.
        """

        return "08006"


class _InvalidPasswordError(psycopg.OperationalError):
    """Permanent authentication failure."""

    @property
    def sqlstate(self) -> str:
        """Return the InvalidPassword SQLSTATE.

        Returns:
            ``28P01``.
        """

        return "28P01"


def test_connect_postgres_retries_transient_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A class-08 failure uses two attempts and a bounded delay."""

    import logging

    attempts = {"count": 0}
    delays: list[float] = []

    def _connect(dsn: str, **kwargs: object) -> object:
        """Fail once, then succeed.

        Args:
            dsn: Caller DSN.
            **kwargs: Driver kwargs.

        Returns:
            Dummy connection on the second attempt.

        Raises:
            _TransientConnectError: First attempt.
        """

        del dsn, kwargs
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise _TransientConnectError("connection failure")
        return object()

    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    with caplog.at_level(
        logging.INFO, logger="smart_rag_core.settings.postgres_connect"
    ):
        connect_postgres(_SESSION, sleep=delays.append)
    assert attempts["count"] == 2
    assert delays == [0.1]
    assert len(caplog.records) == 1
    record = caplog.records[0]
    extra = record.__dict__
    assert extra.get("operation") == "connect_postgres"
    assert extra.get("attempt") == 1
    assert extra.get("reason") == "transient_connect"
    text = caplog.text.casefold()
    assert "postgresql://" not in text
    assert "super-secret" not in text
    assert "connection failure" not in text


def test_connect_postgres_does_not_retry_invalid_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Permanent auth failures use one attempt."""

    attempts = {"count": 0}

    def _connect(dsn: str, **kwargs: object) -> object:
        """Always raise InvalidPassword.

        Args:
            dsn: Caller DSN.
            **kwargs: Driver kwargs.

        Returns:
            Never returns.

        Raises:
            _InvalidPasswordError: Always.
        """

        del dsn, kwargs
        attempts["count"] += 1
        raise _InvalidPasswordError("password authentication failed")

    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    with pytest.raises(_InvalidPasswordError):
        connect_postgres(_SESSION, sleep=lambda _delay: None)
    assert attempts["count"] == 1


def test_connect_postgres_retries_oserror_without_sqlstate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrapped DNS/socket failures with no SQLSTATE are retryable."""

    attempts = {"count": 0}

    def _connect(dsn: str, **kwargs: object) -> object:
        """Fail with TimeoutError, then succeed.

        Args:
            dsn: Caller DSN.
            **kwargs: Driver kwargs.

        Returns:
            Dummy connection on the second attempt.

        Raises:
            TimeoutError: First attempt.
        """

        del dsn, kwargs
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("timed out")
        return object()

    monkeypatch.setattr(
        "smart_rag_core.settings.postgres_connect.psycopg.connect",
        _connect,
    )
    connect_postgres(_SESSION, sleep=lambda _delay: None)
    assert attempts["count"] == 2
