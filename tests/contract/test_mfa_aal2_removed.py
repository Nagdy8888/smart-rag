"""Contract tests that live SQL authorization no longer requires MFA/AAL2."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one Auth user for MFA-removal contract tests.

    Args:
        cursor: Open Postgres cursor.
        user_id: Auth subject.
        email: Unique email.
    """

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


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield a local Supabase connection or skip when unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_live_sql_functions_do_not_require_mfa_or_aal2(
    db_connection: psycopg.Connection,
) -> None:
    """Replacement RPCs must not encode MFA or AAL2 rejection text."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_get_functiondef(p.oid)
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname IN ('reserve_upload_quota', 'accept_invitation')
            """
        )
        definitions = [str(row[0]) for row in cursor.fetchall()]
    assert definitions
    joined = "\n".join(definitions)
    assert "MFA required for upload" not in joined
    assert "requires aal2" not in joined


def test_owner_and_upload_member_reserve_without_mfa(
    db_connection: psycopg.Connection,
) -> None:
    """Owner and upload-enabled members reserve at ordinary assurance without MFA."""

    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    viewer_id = uuid.uuid4()
    blocked_member_id = uuid.uuid4()
    with db_connection.cursor() as cursor:
        for user_id in (owner_id, member_id, viewer_id, blocked_member_id):
            _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (
              user_id, role, upload_enabled, mfa_enrolled, upload_quota_bytes
            )
            VALUES
              (%s, 'owner', false, false, 10000),
              (%s, 'member', true, false, 10000),
              (%s, 'viewer', false, false, 10000),
              (%s, 'member', false, false, 10000)
            """,
            (owner_id, member_id, viewer_id, blocked_member_id),
        )
        cursor.execute("SELECT app.current_authorization_version()")
        version_row = cursor.fetchone()
        assert version_row is not None
        auth_version = int(version_row[0])
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id FROM app.reserve_upload_quota(
              %s, 'owner', %s, 100, 'owner-nomfa', 's', NULL
            )
            """,
            (owner_id, auth_version),
        )
        owner_row = cursor.fetchone()
        assert owner_row is not None
        cursor.execute(
            """
            SELECT reservation_id FROM app.reserve_upload_quota(
              %s, 'member', %s, 100, 'member-nomfa', 's', NULL
            )
            """,
            (member_id, auth_version),
        )
        member_row = cursor.fetchone()
        assert member_row is not None
        cursor.execute("SAVEPOINT viewer_denied")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                SELECT reservation_id FROM app.reserve_upload_quota(
                  %s, 'viewer', %s, 100, 'viewer-nomfa', 's', NULL
                )
                """,
                (viewer_id, auth_version),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT viewer_denied")
        cursor.execute("RELEASE SAVEPOINT viewer_denied")
        cursor.execute("SAVEPOINT member_denied")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                SELECT reservation_id FROM app.reserve_upload_quota(
                  %s, 'member', %s, 100, 'blocked-member', 's', NULL
                )
                """,
                (blocked_member_id, auth_version),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT member_denied")
        cursor.execute("RELEASE SAVEPOINT member_denied")
