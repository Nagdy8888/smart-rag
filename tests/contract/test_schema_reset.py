"""Contract tests for Phase 2 authoritative schema after local Supabase reset."""

from __future__ import annotations

import uuid

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect

KEY_TABLES = (
    "app.profiles",
    "app.company_settings",
    "app.documents",
    "app.document_versions",
    "app.document_chunks",
    "app.ingestion_jobs",
    "app.bm25_index_jobs",
    "app.audit_events",
    "langgraph.checkpoints",
    "lightrag.schema_capture_status",
)


def test_schema_objects_exist_and_invariants_hold() -> None:
    """Prove key tables, vector dim, triggers, and idempotency constraints."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")

    with connection:
        with connection.cursor() as cursor:
            for qualified_name in KEY_TABLES:
                schema, table = qualified_name.split(".", 1)
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    """,
                    (schema, table),
                )
                assert cursor.fetchone() is not None, qualified_name

            cursor.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute AS a
                JOIN pg_class AS c ON c.oid = a.attrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'app'
                  AND c.relname = 'document_chunks'
                  AND a.attname = 'embedding'
                  AND NOT a.attisdropped
                """
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "vector(1024)"

            doc_a = uuid.uuid4()
            doc_b = uuid.uuid4()
            version_a = uuid.uuid4()
            version_b = uuid.uuid4()

            cursor.execute(
                """
                INSERT INTO app.documents (id, title)
                VALUES (%s, 'doc-a'), (%s, 'doc-b')
                """,
                (doc_a, doc_b),
            )
            cursor.execute(
                """
                INSERT INTO app.document_versions (id, document_id, version_number)
                VALUES (%s, %s, 1), (%s, %s, 1)
                """,
                (version_a, doc_a, version_b, doc_b),
            )

            with pytest.raises(
                psycopg.errors.RaiseException, match="belongs to document"
            ):
                cursor.execute("SAVEPOINT cross_document_version")
                cursor.execute(
                    "UPDATE app.documents SET current_version_id = %s WHERE id = %s",
                    (version_b, doc_a),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT cross_document_version")
            cursor.execute("RELEASE SAVEPOINT cross_document_version")

            cursor.execute(
                """
                INSERT INTO app.audit_events (event_type, payload)
                VALUES ('schema_contract', '{}'::jsonb)
                RETURNING id
                """
            )
            audit_row = cursor.fetchone()
            assert audit_row is not None
            audit_id = audit_row[0]

            with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
                cursor.execute("SAVEPOINT audit_update")
                cursor.execute(
                    "UPDATE app.audit_events SET event_type = 'mutated' WHERE id = %s",
                    (audit_id,),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT audit_update")
            cursor.execute("RELEASE SAVEPOINT audit_update")

            with pytest.raises(psycopg.errors.CheckViolation):
                cursor.execute("SAVEPOINT graph_eligible")
                cursor.execute(
                    """
                    INSERT INTO app.documents (title, visibility, graph_eligible)
                    VALUES ('restricted-graph', 'restricted', true)
                    """
                )
            cursor.execute("ROLLBACK TO SAVEPOINT graph_eligible")
            cursor.execute("RELEASE SAVEPOINT graph_eligible")

            cursor.execute(
                """
                INSERT INTO app.ingestion_jobs (job_kind, idempotency_key)
                VALUES ('parse', 'dup-key-1')
                """
            )
            with pytest.raises(psycopg.errors.UniqueViolation):
                cursor.execute("SAVEPOINT dup_job")
                cursor.execute(
                    """
                    INSERT INTO app.ingestion_jobs (job_kind, idempotency_key)
                    VALUES ('parse', 'dup-key-1')
                    """
                )
            cursor.execute("ROLLBACK TO SAVEPOINT dup_job")
            cursor.execute("RELEASE SAVEPOINT dup_job")

        connection.rollback()
