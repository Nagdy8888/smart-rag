"""Owner/admin document title rename. Generic titles only."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest

from tests.contract.integration_support import require_supabase_db_url, try_connect
from tests.contract.test_rls_matrix import rls_auth_version, rls_insert_profile

_GENERIC_TITLE = "Canonical Source Title"


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield a rollback Postgres connection or skip when unreachable.

    Yields:
        Transactional operator connection.

    Side Effects:
        Rolls back every write from the test.
    """

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_update_document_title_owner_admin_and_not_found(
    db_connection: psycopg.Connection,
) -> None:
    """Owner and admin rename; members are forbidden; missing ids match.

    Raises:
        AssertionError: When authorization or validation differs from the
            packet contract.
    """

    owner_id = uuid4()
    admin_id = uuid4()
    member_id = uuid4()
    document_id = uuid4()
    hidden_id = uuid4()
    deleted_id = uuid4()
    version_id = uuid4()

    with db_connection.cursor() as cursor:
        rls_insert_profile(cursor, user_id=owner_id, role="owner")
        rls_insert_profile(cursor, user_id=admin_id, role="admin")
        rls_insert_profile(cursor, user_id=member_id, role="member")
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES
              (%s, 'Original Fixture Title', 'company_visible', %s),
              (%s, 'Hidden restricted', 'restricted', %s),
              (%s, 'Deleted fixture', 'company_visible', %s)
            """,
            (
                document_id,
                owner_id,
                hidden_id,
                owner_id,
                deleted_id,
                owner_id,
            ),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET deleted_at = timezone('utc', now())
            WHERE id = %s
            """,
            (deleted_id,),
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
        chunk_id = uuid4()
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              is_search_representative
            )
            VALUES (%s, %s, %s, 0, 'Fixture passage text', true)
            """,
            (chunk_id, document_id, version_id),
        )
        authz = rls_auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT member_rename")
        with pytest.raises(psycopg.errors.RaiseException, match="documents:forbidden"):
            cursor.execute(
                "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
                (member_id, "member", authz, document_id, _GENERIC_TITLE),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT member_rename")
        cursor.execute("RELEASE SAVEPOINT member_rename")
        cursor.execute(
            "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
            (member_id, "member", authz, hidden_id, _GENERIC_TITLE),
        )
        hidden = cursor.fetchone()
        cursor.execute(
            "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
            (owner_id, "owner", authz, deleted_id, _GENERIC_TITLE),
        )
        deleted = cursor.fetchone()
        cursor.execute(
            "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
            (owner_id, "owner", authz, uuid4(), _GENERIC_TITLE),
        )
        missing = cursor.fetchone()
        cursor.execute("SAVEPOINT empty_title")
        with pytest.raises(
            psycopg.errors.RaiseException, match="documents:invalid_title"
        ):
            cursor.execute(
                "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
                (owner_id, "owner", authz, document_id, "   "),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT empty_title")
        cursor.execute("RELEASE SAVEPOINT empty_title")
        cursor.execute("SAVEPOINT long_title")
        with pytest.raises(
            psycopg.errors.RaiseException, match="documents:invalid_title"
        ):
            cursor.execute(
                "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
                (owner_id, "owner", authz, document_id, "A" * 513),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT long_title")
        cursor.execute("RELEASE SAVEPOINT long_title")
        cursor.execute(
            "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
            (owner_id, "owner", authz, document_id, _GENERIC_TITLE),
        )
        owner_row = cursor.fetchone()
        cursor.execute(
            "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
            (admin_id, "admin", authz, document_id, "Canonical Source Title v2"),
        )
        admin_row = cursor.fetchone()
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT title, current_version_id FROM app.documents WHERE id = %s",
            (document_id,),
        )
        renamed = cursor.fetchone()
        cursor.execute(
            """
            SELECT count(*)
            FROM app.document_search_terms
            WHERE chunk_id = %s
              AND term = 'Canonical Source Title v2'
            """,
            (chunk_id,),
        )
        term_rows = cursor.fetchone()

    assert hidden is not None and hidden[0] is None
    assert deleted is not None and deleted[0] is None
    assert missing is not None and missing[0] is None
    assert owner_row is not None and owner_row[0] == document_id
    assert admin_row is not None and admin_row[0] == document_id
    assert renamed is not None
    assert renamed[0] == "Canonical Source Title v2"
    assert renamed[1] == version_id
    assert term_rows is not None and int(term_rows[0]) >= 1


def test_sync_document_title_search_terms_is_idempotent(
    db_connection: psycopg.Connection,
) -> None:
    """Title sync inserts once on representative chunks and skips duplicates.

    Raises:
        AssertionError: When the title term is missing or duplicated.
    """

    owner_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()

    with db_connection.cursor() as cursor:
        rls_insert_profile(cursor, user_id=owner_id, role="owner")
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES (%s, 'Original Fixture Title', 'company_visible', %s)
            """,
            (document_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status, retrieval_eligible,
              storage_bucket, storage_path
            )
            VALUES (
              %s, %s, 1, 'graph_ineligible', true, 'documents', 'path/object.bin'
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
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              is_search_representative
            )
            VALUES (%s, %s, %s, 0, 'Fixture passage for title terms.', true)
            """,
            (chunk_id, document_id, version_id),
        )
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            "SELECT app.sync_document_title_search_terms(%s, %s)",
            (document_id, _GENERIC_TITLE),
        )
        first = cursor.fetchone()
        cursor.execute(
            "SELECT app.sync_document_title_search_terms(%s, %s)",
            (document_id, _GENERIC_TITLE),
        )
        second = cursor.fetchone()
        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT count(*)
            FROM app.document_search_terms
            WHERE chunk_id = %s
              AND term = %s
            """,
            (chunk_id, _GENERIC_TITLE),
        )
        stored = cursor.fetchone()

    assert first is not None and first[0] == 1
    assert second is not None and second[0] == 0
    assert stored is not None and stored[0] == 1
