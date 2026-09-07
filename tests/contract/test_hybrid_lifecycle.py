"""Contract tests for Hybrid Ready lifecycle with local Supabase and ParadeDB."""

# ruff: noqa: S608

from __future__ import annotations

from collections.abc import Sequence
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
from smart_rag_core.retrieval.bm25_indexer import Bm25Indexer

from tests.contract.integration_support import (
    packet8_paradedb_url,
    paradedb_reachable,
    require_supabase_db_url,
    resolve_supabase_db_url,
    try_connect,
)

pytestmark = pytest.mark.skipif(
    try_connect(resolve_supabase_db_url()) is None or not paradedb_reachable(),
    reason="explicit SUPABASE_DB_URL or ParadeDB unavailable",
)


def _require_row(row: object) -> Sequence[object]:
    """Return a fetched SQL row or fail the current assertion.

    Args:
        row: ``cursor.fetchone()`` result.

    Returns:
        The non-null row as a sequence of column values.
    """

    assert row is not None
    return cast(Sequence[object], row)


def _parade_url() -> str:
    """Return the Packet 8 host ParadeDB writer URL."""

    url = packet8_paradedb_url()
    assert url is not None
    return url


def test_graph_pending_handoff_is_idempotent() -> None:
    """Graph-eligible versions enqueue exactly one pending handoff job."""

    version_id = uuid4()
    document_id = uuid4()
    with psycopg.connect(require_supabase_db_url()) as connection:
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
            first = _require_row(cursor.fetchone())[0]
            cursor.execute(
                "SELECT app.enqueue_graph_pending_handoff(%s, 'hash123')",
                (version_id,),
            )
            second = _require_row(cursor.fetchone())[0]
            cursor.execute(
                """
                SELECT count(*)
                FROM app.lightrag_index_jobs
                WHERE version_id = %s AND operation = 'index'
                """,
                (version_id,),
            )
            count = int(str(_require_row(cursor.fetchone())[0]))
        connection.rollback()

    assert first == second
    assert count == 1


def test_graph_ineligible_replacement_may_flip_current() -> None:
    """Phase 3 may switch current for graph-ineligible verified versions."""

    document_id = uuid4()
    first_id = uuid4()
    second_id = uuid4()
    with psycopg.connect(require_supabase_db_url()) as connection:
        connection.execute("SET ROLE postgres")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.documents (id, title, visibility, graph_eligible)
                VALUES (%s, 'Ineligible Replacement', 'restricted', false)
                """,
                (document_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (
                  id, document_id, version_number, status, graph_eligible, is_current
                )
                VALUES
                  (%s, %s, 1, 'hybrid_ready', false, true),
                  (%s, %s, 2, 'hybrid_ready', false, false)
                """,
                (first_id, document_id, second_id, document_id),
            )
            cursor.execute(
                "UPDATE app.documents SET current_version_id = %s WHERE id = %s",
                (first_id, document_id),
            )
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_version_id FROM app.activate_graph_ineligible_version(%s)",
                (second_id,),
            )
            current = _require_row(cursor.fetchone())[0]
            cursor.execute(
                "SELECT is_current FROM app.document_versions WHERE id = %s",
                (second_id,),
            )
            second_current = _require_row(cursor.fetchone())[0]
            cursor.execute(
                "SELECT is_current FROM app.document_versions WHERE id = %s",
                (first_id,),
            )
            first_current = _require_row(cursor.fetchone())[0]
        connection.rollback()
    assert current == second_id
    assert second_current is True
    assert first_current is False


def test_graph_eligible_replacement_stays_non_current() -> None:
    """Graph-eligible replacements wait for Phase 5 and must not flip current."""

    document_id = uuid4()
    version_id = uuid4()
    with psycopg.connect(require_supabase_db_url()) as connection:
        connection.execute("SET ROLE postgres")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.documents (id, title, visibility, graph_eligible)
                VALUES (%s, 'Eligible Replacement', 'company_visible', false)
                """,
                (document_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (
                  id, document_id, version_number, status, graph_eligible, is_current
                )
                VALUES (%s, %s, 1, 'hybrid_ready', true, false)
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
            cursor.execute("SAVEPOINT deny_eligible")
            with pytest.raises(psycopg.errors.RaiseException):
                cursor.execute(
                    "SELECT app.activate_graph_ineligible_version(%s)",
                    (version_id,),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT deny_eligible")
            cursor.execute(
                "SELECT is_current FROM app.document_versions WHERE id = %s",
                (version_id,),
            )
            is_current = _require_row(cursor.fetchone())[0]
        connection.rollback()
    assert is_current is False


def test_deletion_excludes_retrieval_and_enqueues_bm25_cleanup() -> None:
    """Deletion/ACL exclusion is immediate in Supabase with high-priority cleanup."""

    version_id = uuid4()
    document_id = uuid4()
    with psycopg.connect(require_supabase_db_url()) as connection:
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

    version_values = _require_row(version_row)
    bm25_values = _require_row(bm25_row)
    assert version_values[0] is False
    assert version_values[1] == "deletion_pending"
    assert bm25_values[0] == "high"
    assert bm25_values[1] == "delete"


@pytest.mark.skipif(
    packet8_paradedb_url() is None or try_connect(packet8_paradedb_url() or "") is None,
    reason="Packet 8 ParadeDB overlay required for host-side psycopg contracts",
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
    with (
        psycopg.connect(require_supabase_db_url()) as supabase,
        psycopg.connect(parade_url, connect_timeout=5) as parade,
    ):
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


def test_hybrid_ready_blocked_without_processing_bm25_job() -> None:
    """finalize_hybrid_ready cannot flip Hybrid Ready before BM25 verify."""

    version_id = uuid4()
    document_id = uuid4()
    with psycopg.connect(require_supabase_db_url()) as connection:
        connection.execute("SET ROLE postgres")
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO app.documents (id, title) VALUES (%s, 'Hybrid gate')",
                (document_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (
                  id, document_id, version_number, status, chunk_set_hash
                )
                VALUES (%s, %s, 1, 'parsing', 'hash-gate')
                """,
                (version_id, document_id),
            )
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute("SAVEPOINT deny_hybrid")
            with pytest.raises(psycopg.Error):
                cursor.execute(
                    "SELECT app.finalize_hybrid_ready(%s, 'hash-gate', NULL)",
                    (version_id,),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT deny_hybrid")
            cursor.execute(
                "SELECT status, hybrid_verified_at, bm25_verified_at "
                "FROM app.document_versions WHERE id = %s",
                (version_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "parsing"
            assert row[1] is None
            assert row[2] is None
        connection.rollback()


def test_finalize_hybrid_ready_sets_current_for_graph_ineligible() -> None:
    """Production finalize points retrieval at graph-ineligible Hybrid Ready."""

    version_id = uuid4()
    document_id = uuid4()
    job_id = uuid4()
    with psycopg.connect(require_supabase_db_url()) as connection:
        connection.execute("SET ROLE postgres")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.documents (id, title, visibility, graph_eligible)
                VALUES (%s, 'Ineligible pointer', 'restricted', false)
                """,
                (document_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (
                  id, document_id, version_number, status, graph_eligible,
                  chunk_set_hash, is_current
                )
                VALUES (%s, %s, 1, 'parsing', false, 'hash-ineligible', false)
                """,
                (version_id, document_id),
            )
            cursor.execute(
                """
                INSERT INTO app.bm25_index_jobs (
                  id, version_id, operation, status, idempotency_key
                )
                VALUES (
                  %s, %s, 'upsert'::app.bm25_job_operation,
                  'processing'::app.job_status, %s
                )
                """,
                (job_id, version_id, f"bm25:upsert:{version_id}:hash-ineligible"),
            )
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app.finalize_hybrid_ready(%s, 'hash-ineligible', %s)",
                (version_id, job_id),
            )
            cursor.execute(
                """
                SELECT d.current_version_id, dv.is_current, dv.status
                FROM app.documents AS d
                JOIN app.document_versions AS dv ON dv.id = %s
                WHERE d.id = %s
                """,
                (version_id, document_id),
            )
            row = cursor.fetchone()
        connection.rollback()
    assert row is not None
    assert row[0] == version_id
    assert row[1] is True
    assert row[2] == "graph_ineligible"


def test_finalize_hybrid_ready_keeps_graph_eligible_non_current() -> None:
    """Graph-eligible replacements must not become current in Phase 3 finalize."""

    document_id = uuid4()
    old_id = uuid4()
    new_id = uuid4()
    job_id = uuid4()
    with psycopg.connect(require_supabase_db_url()) as connection:
        connection.execute("SET ROLE postgres")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.documents (id, title, visibility, graph_eligible)
                VALUES (%s, 'Eligible pointer', 'company_visible', false)
                """,
                (document_id,),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (
                  id, document_id, version_number, status, graph_eligible,
                  chunk_set_hash, is_current
                )
                VALUES
                  (%s, %s, 1, 'hybrid_ready', true, 'hash-old', true),
                  (%s, %s, 2, 'parsing', true, 'hash-new', false)
                """,
                (old_id, document_id, new_id, document_id),
            )
            cursor.execute(
                """
                UPDATE app.documents
                SET current_version_id = %s, graph_eligible = true
                WHERE id = %s
                """,
                (old_id, document_id),
            )
            cursor.execute(
                """
                INSERT INTO app.bm25_index_jobs (
                  id, version_id, operation, status, idempotency_key
                )
                VALUES (
                  %s, %s, 'upsert'::app.bm25_job_operation,
                  'processing'::app.job_status, %s
                )
                """,
                (job_id, new_id, f"bm25:upsert:{new_id}:hash-new"),
            )
        connection.execute("SET ROLE app_worker")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app.finalize_hybrid_ready(%s, 'hash-new', %s)",
                (new_id, job_id),
            )
            cursor.execute(
                "SELECT current_version_id FROM app.documents WHERE id = %s",
                (document_id,),
            )
            current = cursor.fetchone()
            cursor.execute(
                "SELECT is_current, status FROM app.document_versions WHERE id = %s",
                (new_id,),
            )
            new_row = cursor.fetchone()
            cursor.execute(
                "SELECT is_current FROM app.document_versions WHERE id = %s",
                (old_id,),
            )
            old_row = cursor.fetchone()
        connection.rollback()
    assert current is not None
    assert current[0] == old_id
    assert new_row is not None
    assert new_row[0] is False
    assert new_row[1] == "graph_pending"
    assert old_row is not None
    assert old_row[0] is True
