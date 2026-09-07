"""Graph eligibility and ACL-downgrade Storage packet contract tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from tests.contract.integration_support import require_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row for graph eligibility tests."""

    cursor.execute(
        """
        INSERT INTO auth.users (
          id, instance_id, aud, role, email, encrypted_password,
          email_confirmed_at, created_at, updated_at
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
    """Return the live company authorization_version."""

    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_assert_graph_index_rejects_restricted_non_current_deleted(
    db_connection: psycopg.Connection,
) -> None:
    """Restricted, non-current, and deleted documents fail assert_graph_index_allowed."""

    admin = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_a = uuid.uuid4()
    version_b = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, admin, f"{admin}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, mfa_enrolled)
            VALUES (%s, 'admin', true)
            """,
            (admin,),
        )
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by, graph_eligible)
            VALUES (%s, 'Doc', 'company_visible', %s, false)
            """,
            (doc_id, admin),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by
            )
            VALUES
              (%s, %s, 1, %s),
              (%s, %s, 2, %s)
            """,
            (version_a, doc_id, admin, version_b, doc_id, admin),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s, graph_eligible = true
            WHERE id = %s
            """,
            (version_a, doc_id),
        )

        cursor.execute(
            "SELECT app.assert_graph_index_allowed(%s, %s)",
            (doc_id, version_a),
        )
        allowed = cursor.fetchone()
        assert allowed is not None
        assert allowed[0] is True

        cursor.execute("SAVEPOINT non_current")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                "SELECT app.assert_graph_index_allowed(%s, %s)",
                (doc_id, version_b),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT non_current")
        cursor.execute("RELEASE SAVEPOINT non_current")

        auth_version = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT visibility, graph_eligible
            FROM app.set_document_visibility(
              %s, 'admin', %s, %s, 'restricted'
            )
            """,
            (admin, auth_version, doc_id),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "restricted"
        assert row[1] is False

        cursor.execute("SAVEPOINT restricted_assert")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                "SELECT app.assert_graph_index_allowed(%s, %s)",
                (doc_id, version_a),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_assert")
        cursor.execute("RELEASE SAVEPOINT restricted_assert")

        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT count(*)
            FROM app.lightrag_index_jobs
            WHERE document_id = %s
              AND operation = 'graph_acl_remove'
            """,
            (doc_id,),
        )
        cleanup_jobs = cursor.fetchone()
        assert cleanup_jobs is not None
        assert cleanup_jobs[0] >= 1

        cursor.execute(
            """
            UPDATE app.documents
            SET visibility = 'company_visible',
                graph_eligible = false,
                deleted_at = timezone('utc', now())
            WHERE id = %s
            """,
            (doc_id,),
        )
        cursor.execute("SAVEPOINT deleted_assert")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                "SELECT app.assert_graph_index_allowed(%s, NULL)",
                (doc_id,),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT deleted_assert")
        cursor.execute("RELEASE SAVEPOINT deleted_assert")


def test_index_job_trigger_uses_assert_gate(
    db_connection: psycopg.Connection,
) -> None:
    """Normal graph index jobs are rejected for restricted documents."""

    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES (%s, 'Restricted', 'restricted', %s)
            """,
            (doc_id, user_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by
            )
            VALUES (%s, %s, 1, %s)
            """,
            (version_id, doc_id, user_id),
        )
        cursor.execute(
            "UPDATE app.documents SET current_version_id = %s WHERE id = %s",
            (version_id, doc_id),
        )
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                INSERT INTO app.lightrag_index_jobs (
                  document_id, version_id, operation, idempotency_key
                )
                VALUES (%s, %s, 'index', %s)
                """,
                (doc_id, version_id, f"idx-{uuid.uuid4()}"),
            )


def test_admin_notification_helper_and_fixtures(
    db_connection: psycopg.Connection,
) -> None:
    """emit_admin_notification appends without raw long-retention content."""

    with db_connection.cursor() as cursor:
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT app.emit_admin_notification(
              'byte_spike',
              'warning',
              'Test spike',
              'metadata only',
              jsonb_build_object('bytes', 100, 'raw_content', NULL)
            )
            """
        )
        note_id_row = cursor.fetchone()
        assert note_id_row is not None
        note_id = note_id_row[0]
        assert note_id is not None
        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT notification_kind
            FROM app.admin_notifications
            WHERE notification_kind IN (
              'byte_spike',
              'quarantine_accumulation',
              'repeated_scan_failure',
              'unusual_crawl_domain'
            )
              AND metadata->>'fixture' = 'true'
            """
        )
        kinds = {row[0] for row in cursor.fetchall()}
        assert kinds == {
            "byte_spike",
            "quarantine_accumulation",
            "repeated_scan_failure",
            "unusual_crawl_domain",
        }
