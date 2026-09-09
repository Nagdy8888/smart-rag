"""Scoped timeouts for long-document canonical and embedding-ledger writes."""

from __future__ import annotations

import re

import psycopg

from smart_rag_core.ingestion.limits import (
    LONG_DOCUMENT_IDLE_IN_TXN_TIMEOUT,
    LONG_DOCUMENT_WRITE_STATEMENT_TIMEOUT,
)

_TIMEOUT_TOKEN = re.compile(r"^[0-9]+s$")


def apply_long_document_write_timeouts(connection: psycopg.Connection) -> None:
    """Raise statement and idle-in-txn timeouts for one worker transaction.

    The ``app_worker`` role default remains 60s / 15s. This only ``SET LOCAL``
    for the current transaction so hundreds of vector inserts or a large
    ledger write can finish without changing login GUCs.

    Args:
        connection: Open worker-role connection already inside a transaction.

    Raises:
        ValueError: If a timeout constant is not an ``Ns`` token.

    Side Effects:
        Issues two ``SET LOCAL`` statements. Does not commit.
    """

    statement = LONG_DOCUMENT_WRITE_STATEMENT_TIMEOUT
    idle = LONG_DOCUMENT_IDLE_IN_TXN_TIMEOUT
    if _TIMEOUT_TOKEN.fullmatch(statement) is None:
        raise ValueError("long_document_statement_timeout_invalid")
    if _TIMEOUT_TOKEN.fullmatch(idle) is None:
        raise ValueError("long_document_idle_timeout_invalid")
    connection.execute(f"SET LOCAL statement_timeout = '{statement}'")
    connection.execute(f"SET LOCAL idle_in_transaction_session_timeout = '{idle}'")
