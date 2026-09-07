"""Canonical mid-batch crash rollback on local Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest

from tests.contract.integration_support import (
    read_process_env,
    require_supabase_db_url,
    try_connect,
)


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield Postgres or skip unless the job integration gate is required."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Canonical crash test requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_canonical_transaction_rollback_mid_batch(
    db_connection: psycopg.Connection,
) -> None:
    """Partial canonical chunk writes disappear when the worker transaction rolls back."""

    document_id = uuid4()
    version_id = uuid4()
    chunk_a = uuid4()
    chunk_b = uuid4()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app.documents (id, title) VALUES (%s, 'crash-canonical')",
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (id, document_id, version_number, status)
            VALUES (%s, %s, 1, 'parsing')
            """,
            (version_id, document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text
            )
            VALUES (%s, %s, %s, 0, 'first chunk')
            """,
            (chunk_a, document_id, version_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text
            )
            VALUES (%s, %s, %s, 1, 'second chunk never committed')
            """,
            (chunk_b, document_id, version_id),
        )
        cursor.execute(
            "SELECT count(*) FROM app.document_chunks WHERE version_id = %s",
            (version_id,),
        )
        mid = cursor.fetchone()
        assert mid is not None
        assert mid[0] == 2
    db_connection.rollback()
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM app.document_chunks WHERE version_id = %s",
            (version_id,),
        )
        after = cursor.fetchone()
        assert after is not None
        assert after[0] == 0
