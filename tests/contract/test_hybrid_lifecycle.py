"""Contract tests for Hybrid Ready lifecycle with local Supabase and ParadeDB."""

# ruff: noqa: S608

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer

from tests.contract.integration_support import (
    paradedb_reachable,
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)

pytestmark = pytest.mark.skipif(
    try_connect(resolve_supabase_db_url()) is None or not paradedb_reachable(),
    reason="local Supabase or ParadeDB unavailable",
)


def _parade_url() -> str:
    return read_process_env("PARADEDB_URL") or (
        "postgresql://paradedb_writer:change-me-paradedb-writer@127.0.0.1:5432/paradedb"
    )


def test_graph_pending_handoff_is_idempotent() -> None:
    """Graph-eligible versions enqueue exactly one pending handoff job."""

    version_id = uuid4()
    document_id = uuid4()
    with psycopg.connect(resolve_supabase_db_url()) as connection:
        connection.execute("SET ROLE postgres")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.documents (id, title, visibility, graph_eligible)
                VALUES (%s, 'Synthetic Policy', 'company_visible', false)
                """,
                (document_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (
                  id, document_id, version_number, status, graph_eligible, chunk_set_hash
                )
                VALUES (%s, %s, 1, 'hybrid_ready', true, 'hash123')
                """,
                (version_id, document_id),
            )
            cursor.execute(
                """
                UPDATE app.documents
                SET current_version_id = %s, graph_eligible = true
                WHERE id = %s
                """,
                (version_id, document_id),
            )
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app.enqueue_graph_pending_handoff(%s, 'hash123')",
                (version_id,),
            )
            first = cursor.fetchone()[0]
            cursor.execute(
                "SELECT app.enqueue_graph_pending_handoff(%s, 'hash123')",
                (version_id,),
            )
            second = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT count(*)
                FROM app.lightrag_index_jobs
                WHERE version_id = %s AND operation = 'index'
                """,
                (version_id,),
            )
            count = int(cursor.fetchone()[0])
        connection.rollback()

    assert first == second
    assert count == 1


def test_deletion_excludes_retrieval_and_enqueues_bm25_cleanup() -> None:
    """Deletion/ACL exclusion is immediate in Supabase with high-priority cleanup."""

    version_id = uuid4()
    document_id = uuid4()
    with psycopg.connect(resolve_supabase_db_url()) as connection:
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.documents (id, title, visibility, graph_eligible)
                VALUES (%s, 'Restricted', 'restricted', false)
                """,
                (document_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (
                  id, document_id, version_number, status, retrieval_eligible
                )
                VALUES (%s, %s, 1, 'hybrid_ready', true)
                """,
                (version_id, document_id),
            )
            cursor.execute(
                "SELECT app.exclude_version_from_retrieval(%s, 'test_delete')",
                (version_id,),
            )
            cursor.execute(
                """
                SELECT retrieval_eligible, status
                FROM app.document_versions
                WHERE id = %s
                """,
                (version_id,),
            )
            version_row = cursor.fetchone()
            cursor.execute(
                """
                SELECT priority, operation
                FROM app.bm25_index_jobs
                WHERE version_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (version_id,),
            )
            bm25_row = cursor.fetchone()
        connection.rollback()

    assert version_row[0] is False
    assert version_row[1] == "deletion_pending"
    assert bm25_row[0] == "high"
    assert bm25_row[1] == "delete"


@pytest.mark.skipif(
    read_process_env("PARADEDB_URL") is None,
    reason="PARADEDB_URL required for host-side ParadeDB psycopg contracts",
)
def test_bm25_delete_job_clears_parade_projection() -> None:
    """High-priority delete jobs remove ParadeDB rows for a version."""

    from smart_rag_core.retrieval.bm25_indexer import Bm25ProjectionRow

    version_id = uuid4()
    chunk_id = uuid4()
    parade_url = _parade_url()
    with psycopg.connect(parade_url, connect_timeout=5) as parade:
        parade.execute("SET ROLE paradedb_writer")
        indexer = Bm25Indexer(parade)
        indexer.ensure_projection_schema()
        indexer.upsert_batch(
            (
                Bm25ProjectionRow(
                    chunk_id=chunk_id,
                    version_id=version_id,
                    document_id=uuid4(),
                    title_search="title",
                    heading_search=None,
                    alias_search=None,
                    body_search="annual leave policy",
                    language="en",
                    acl_scope_id="company_visible",
                    is_current=True,
                    visibility_generation=1,
                    normalization_version="arabic_norm_v1",
                    content_hash="abc",
                ),
            )
        )
        parade.commit()
    with psycopg.connect(resolve_supabase_db_url()) as supabase, psycopg.connect(
        parade_url, connect_timeout=5
    ) as parade:
        supabase.execute("SET ROLE app_worker")
        parade.execute("SET ROLE paradedb_writer")
        service = Bm25ProjectionService(supabase, parade)
        assert service.process_delete_job(version_id=version_id) is True
        assert Bm25Indexer(parade).count_rows_for_version(version_id) == 0


def test_paradedb_delete_sql_clears_version_rows() -> None:
    """ParadeDB delete SQL removes all rows for one version via compose exec."""

    from tests.contract.integration_support import paradedb_psql

    version_id = uuid4()
    chunk_id = uuid4()
    document_id = uuid4()
    setup = (
        f"INSERT INTO bm25_chunks (chunk_id, version_id, document_id, body_search, acl_scope_id) "
        f"VALUES ('{chunk_id}', '{version_id}', '{document_id}', "
        f"'annual leave policy', 'company_visible') "
        f"ON CONFLICT (chunk_id) DO UPDATE SET version_id = EXCLUDED.version_id;"
    )
    delete = f"DELETE FROM bm25_chunks WHERE version_id = '{version_id}';"
    count = f"SELECT count(*) FROM bm25_chunks WHERE version_id = '{version_id}';"
    assert paradedb_psql(setup, user="paradedb_writer").returncode == 0
    assert paradedb_psql(delete, user="paradedb_writer").returncode == 0
    completed = paradedb_psql(count, user="paradedb_writer")
    assert completed.returncode == 0
    assert completed.stdout.strip() == "0"
