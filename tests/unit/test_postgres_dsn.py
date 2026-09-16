"""Session/direct Postgres DSN guards never echo secrets."""

from __future__ import annotations

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
