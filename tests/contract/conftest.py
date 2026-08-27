"""Shared local-Supabase fixtures for contract tests that need Postgres."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from tests.contract.integration_support import (
    refuse_hosted_destructive_dsn,
    resolve_supabase_db_url,
    try_connect,
)


@pytest.fixture
def db_url() -> str:
    """Return the local Supabase URL or skip when the stack is down.

    Returns:
        Postgres DSN for the local fixture database.

    Raises:
        pytest.skip: When the local stack is unreachable.
    """

    url = resolve_supabase_db_url()
    refuse_hosted_destructive_dsn(url)
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.close()
    return url


@pytest.fixture
def db_connection(db_url: str) -> Iterator[psycopg.Connection]:
    """Yield one rollback Postgres connection for a contract test.

    Args:
        db_url: Local Supabase DSN from ``db_url``.

    Yields:
        Open ``postgres``-role connection. Callers ``SET ROLE`` as needed.
    """

    connection = psycopg.connect(db_url)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()
