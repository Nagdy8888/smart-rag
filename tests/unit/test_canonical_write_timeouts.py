"""Unit tests for long-document canonical write timeouts."""

from __future__ import annotations

from smart_rag_core.ingestion.canonical.timeouts import (
    apply_long_document_write_timeouts,
)
from smart_rag_core.ingestion.limits import (
    LONG_DOCUMENT_IDLE_IN_TXN_TIMEOUT,
    LONG_DOCUMENT_WRITE_STATEMENT_TIMEOUT,
)


def test_apply_long_document_write_timeouts_sets_local_only() -> None:
    """Worker role defaults stay 60s; this transaction SET LOCAL is 300s/180s."""

    statements: list[str] = []

    class _Connection:
        """Connection double that records SET LOCAL statements."""

        def execute(self, sql: str, *_args: object) -> None:
            """Record one statement.

            Args:
                sql: SQL text.
                *_args: Unused bind parameters.
            """

            statements.append(sql)

    apply_long_document_write_timeouts(_Connection())  # type: ignore[arg-type]
    assert statements == [
        f"SET LOCAL statement_timeout = '{LONG_DOCUMENT_WRITE_STATEMENT_TIMEOUT}'",
        (
            "SET LOCAL idle_in_transaction_session_timeout = "
            f"'{LONG_DOCUMENT_IDLE_IN_TXN_TIMEOUT}'"
        ),
    ]
    assert LONG_DOCUMENT_WRITE_STATEMENT_TIMEOUT == "300s"
    assert LONG_DOCUMENT_IDLE_IN_TXN_TIMEOUT == "180s"
