"""Owner/admin document delete wraps exclude_version_from_retrieval (PRD-H-031)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect
from tests.contract.test_rls_matrix import rls_auth_version, rls_insert_profile


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield a rollback Postgres connection or skip when local Supabase is down."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_delete_visible_document_excludes_retrieval_and_hides_from_members(
    db_connection: psycopg.Connection,
) -> None:
    """Owner delete tombstones, drops current_version, and enqueues BM25 delete."""

    owner_id = uuid4()
    member_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    hidden_id = uuid4()

    with db_connection.cursor() as cursor:
        rls_insert_profile(cursor, user_id=owner_id, role="owner")
        rls_insert_profile(cursor, user_id=member_id, role="member")
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES
              (%s, 'Delete fixture', 'company_visible', %s),
              (%s, 'Hidden restricted', 'restricted', %s)
            """,
            (document_id, owner_id, hidden_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status, retrieval_eligible,
              storage_bucket, storage_path
            )
            VALUES (
              %s, %s, 1, 'hybrid_ready', true, 'documents', 'path/object.bin'
            )
            """,
            (version_id, document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s
            WHERE id = %s
            """,
            (version_id, document_id),
        )
        authz = rls_auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT member_delete")
        with pytest.raises(psycopg.errors.RaiseException, match="documents:forbidden"):
            cursor.execute(
                "SELECT app.delete_visible_document(%s, %s, %s, %s)",
                (member_id, "member", authz, document_id),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT member_delete")
        cursor.execute("RELEASE SAVEPOINT member_delete")
        cursor.execute(
            "SELECT app.delete_visible_document(%s, %s, %s, %s)",
            (member_id, "member", authz, hidden_id),
        )
        hidden = cursor.fetchone()
        cursor.execute(
            "SELECT app.delete_visible_document(%s, %s, %s, %s)",
            (owner_id, "owner", authz, document_id),
        )
        deleted = cursor.fetchone()
        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT deleted_at IS NOT NULL, current_version_id
            FROM app.documents
            WHERE id = %s
            """,
            (document_id,),
        )
        document_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT retrieval_eligible, status::text
            FROM app.document_versions
            WHERE id = %s
            """,
            (version_id,),
        )
        version_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT operation::text, payload_ref ->> 'storage_path'
            FROM app.bm25_index_jobs
            WHERE version_id = %s
              AND operation = 'delete'::app.bm25_job_operation
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (version_id,),
        )
        bm25_row = cursor.fetchone()

    assert hidden is not None
    assert hidden[0] is None
    assert deleted is not None
    assert deleted[0] == document_id
    assert document_row is not None
    assert document_row[0] is True
    assert document_row[1] is None
    assert version_row == (False, "deletion_pending")
    assert bm25_row == ("delete", "path/object.bin")
