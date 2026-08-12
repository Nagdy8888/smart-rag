"""RLS matrix and identity propagation contract tests (Phase 2 Packet 3)."""

from __future__ import annotations

import uuid

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row for profile FK tests."""

    cursor.execute(
        """
        INSERT INTO auth.users (
          id,
          instance_id,
          aud,
          role,
          email,
          encrypted_password,
          email_confirmed_at,
          created_at,
          updated_at
        )
        VALUES (
          %s,
          '00000000-0000-0000-0000-000000000000'::uuid,
          'authenticated',
          'authenticated',
          %s,
          crypt('test-password', gen_salt('bf')),
          timezone('utc', now()),
          timezone('utc', now()),
          timezone('utc', now())
        )
        ON CONFLICT (id) DO NOTHING
        """,
        (user_id, email),
    )


def _auth_version(cursor: psycopg.Cursor) -> int:
    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture
def db_connection() -> psycopg.Connection:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_rls_matrix_documents_conversations_and_audit(
    db_connection: psycopg.Connection,
) -> None:
    """Prove forged/stale RPC context, ACL, creator privacy, and audit immutability."""

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    restricted_doc = uuid.uuid4()
    visible_doc = uuid.uuid4()
    conversation_a = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_a, f"{user_a}@example.com")
        _insert_auth_user(cursor, user_b, f"{user_b}@example.com")

        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, display_name)
            VALUES
              (%s, 'member', 'User A'),
              (%s, 'member', 'User B')
            """,
            (user_a, user_b),
        )

        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES
              (%s, 'Restricted Doc', 'restricted', %s),
              (%s, 'Company Doc', 'company_visible', %s)
            """,
            (restricted_doc, user_a, visible_doc, user_a),
        )

        cursor.execute(
            """
            INSERT INTO app.conversations (id, creator_user_id, title)
            VALUES (%s, %s, 'Private thread')
            """,
            (conversation_a, user_a),
        )

        auth_version = _auth_version(cursor)

        cursor.execute("SET ROLE app_api")

        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_a, auth_version),
        )
        visible_ids = {row[0] for row in cursor.fetchall()}
        assert visible_doc in visible_ids
        assert restricted_doc not in visible_ids

        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_b, auth_version),
        )
        forged_ids = {row[0] for row in cursor.fetchall()}
        assert visible_doc in forged_ids
        assert restricted_doc not in forged_ids

        cursor.execute(
            """
            SELECT count(*)
            FROM app.list_visible_documents(%s, 'admin', %s)
            """,
            (user_b, auth_version),
        )
        assert cursor.fetchone()[0] == 0

        cursor.execute(
            """
            SELECT count(*)
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_a, auth_version - 1),
        )
        assert cursor.fetchone()[0] == 0

        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            INSERT INTO app.document_acl (document_id, grantee_user_id, granted_by)
            VALUES (%s, %s, %s)
            """,
            (restricted_doc, user_a, user_a),
        )
        auth_version = _auth_version(cursor)

        cursor.execute("SET ROLE app_api")

        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_a, auth_version),
        )
        granted_ids = {row[0] for row in cursor.fetchall()}
        assert restricted_doc in granted_ids

        cursor.execute(
            """
            SELECT id
            FROM app.list_user_conversations(%s, 'member', %s)
            """,
            (user_a, auth_version),
        )
        conv_ids = {row[0] for row in cursor.fetchall()}
        assert conversation_a in conv_ids

        cursor.execute(
            """
            SELECT id
            FROM app.list_user_conversations(%s, 'member', %s)
            """,
            (user_b, auth_version),
        )
        other_conv_ids = {row[0] for row in cursor.fetchall()}
        assert conversation_a not in other_conv_ids

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_audit_writer")

        cursor.execute(
            """
            SELECT app.append_audit_event(
              'rls_matrix_test',
              %s,
              'member'::app.user_role,
              'document',
              %s,
              %s,
              '{}'::jsonb
            )
            """,
            (user_a, visible_doc, auth_version),
        )
        audit_id = cursor.fetchone()[0]

        with pytest.raises(
            (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)
        ):
            cursor.execute("SAVEPOINT audit_writer_update")
            cursor.execute(
                "UPDATE app.audit_events SET event_type = 'mutated' WHERE id = %s",
                (audit_id,),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_writer_update")
        cursor.execute("RELEASE SAVEPOINT audit_writer_update")

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_worker")

        version_id = uuid.uuid4()
        cursor.execute(
            """
            INSERT INTO app.document_versions (id, document_id, version_number)
            VALUES (%s, %s, 1)
            """,
            (version_id, restricted_doc),
        )

        with pytest.raises(
            psycopg.errors.RaiseException, match="graph index job rejected"
        ):
            cursor.execute("SAVEPOINT restricted_graph_job")
            cursor.execute(
                """
                INSERT INTO app.lightrag_index_jobs (
                  document_id,
                  version_id,
                  operation,
                  idempotency_key
                )
                VALUES (%s, %s, 'index', %s)
                """,
                (restricted_doc, version_id, f"graph-{uuid.uuid4()}"),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_graph_job")
        cursor.execute("RELEASE SAVEPOINT restricted_graph_job")

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_worker")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("SAVEPOINT worker_conversation_read")
            cursor.execute("SELECT 1 FROM app.conversations LIMIT 1")
        cursor.execute("ROLLBACK TO SAVEPOINT worker_conversation_read")
        cursor.execute("RELEASE SAVEPOINT worker_conversation_read")

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_api")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("SAVEPOINT api_direct_write")
            cursor.execute(
                """
                INSERT INTO app.documents (title)
                VALUES ('direct write attempt')
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT api_direct_write")
        cursor.execute("RELEASE SAVEPOINT api_direct_write")

        cursor.execute("RESET ROLE")


def test_browser_roles_denied_direct_app_access(
    db_connection: psycopg.Connection,
) -> None:
    """Prove anon/authenticated cannot read canonical evidence tables directly."""

    with db_connection.cursor() as cursor:
        for role_name in ("anon", "authenticated"):
            cursor.execute(f"SET ROLE {role_name}")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute("SAVEPOINT browser_select")
                cursor.execute("SELECT 1 FROM app.documents LIMIT 1")
            cursor.execute("ROLLBACK TO SAVEPOINT browser_select")
            cursor.execute("RELEASE SAVEPOINT browser_select")
            cursor.execute("RESET ROLE")


def test_visibility_change_bumps_authorization_and_bm25_job(
    db_connection: psycopg.Connection,
) -> None:
    """Prove visibility flips increment authorization_version and enqueue BM25 intent."""

    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role)
            VALUES (%s, 'admin')
            """,
            (user_id,),
        )

        before_version = _auth_version(cursor)

        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility)
            VALUES (%s, 'Flip me', 'company_visible')
            """,
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (id, document_id, version_number)
            VALUES (%s, %s, 1)
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
            UPDATE app.documents
            SET visibility = 'restricted'
            WHERE id = %s
            """,
            (document_id,),
        )

        after_version = _auth_version(cursor)
        assert after_version == before_version + 1

        cursor.execute(
            """
            SELECT count(*)
            FROM app.bm25_index_jobs
            WHERE payload_ref ->> 'document_id' = %s
              AND idempotency_key LIKE %s
            """,
            (str(document_id), "visibility:%"),
        )
        assert cursor.fetchone()[0] >= 1

        cursor.execute(
            """
            SELECT visibility_generation
            FROM app.documents
            WHERE id = %s
            """,
            (document_id,),
        )
        assert cursor.fetchone()[0] >= 2
