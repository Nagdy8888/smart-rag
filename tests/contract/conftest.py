"""Shared Postgres fixtures for opt-in DB-backed contract tests."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from tests.contract.integration_support import (
    require_supabase_db_url,
    try_connect,
)


@pytest.fixture
def db_url() -> str:
    """Return an explicit non-hosted Postgres DSN or skip.

    Returns:
        Postgres DSN from ``SUPABASE_DB_URL``.

    Raises:
        pytest.skip: When the DSN is unset or the database is unreachable.
    """

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Postgres unreachable at {url}")
    connection.close()
    return url


@pytest.fixture
def db_connection(db_url: str) -> Iterator[psycopg.Connection]:
    """Yield one rollback Postgres connection for a contract test.

    Args:
        db_url: Explicit DSN from ``db_url``.

    Yields:
        Open ``postgres``-role connection. Callers ``SET ROLE`` as needed.
    """

    connection = psycopg.connect(db_url)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()
