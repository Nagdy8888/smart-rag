"""Upload finalization RPC contract tests."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal auth user."""

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
    """Return live authorization version."""

    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_finalize_quarantine_upload_idempotent_and_wrong_path_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Finalize creates one job; cross-user reservation access is rejected."""

    user_id = uuid.uuid4()
    other_id = uuid.uuid4()
    content = b"synthetic-fixture"
    digest = hashlib.sha256(content).hexdigest()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        _insert_auth_user(cursor, other_id, f"{other_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'member', true, true), (%s, 'member', true, true)
            """,
            (user_id, other_id),
        )
        auth_version = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, %s, 'finalize-idem', 'sess', NULL
            )
            """,
            (user_id, auth_version, len(content)),
        )
        reservation_row = cursor.fetchone()
        assert reservation_row is not None
        reservation_id = reservation_row[0]
        cursor.execute(
            """
            SELECT status
            FROM app.finalize_upload_quota(%s, 'member', %s, %s, %s)
            """,
            (user_id, auth_version, reservation_id, len(content)),
        )
        assert cursor.fetchone() is not None
        object_name = f"{user_id}/{reservation_id}/sample.txt"
        cursor.execute(
            """
            SELECT document_id, version_id, job_id
            FROM app.finalize_quarantine_upload(
              %s, 'member', %s, %s, %s, %s, %s,
              'text/plain', 'allowed', '2026-08-13', 'job-idem-1', 'Sample'
            )
            """,
            (user_id, auth_version, reservation_id, object_name, digest, len(content)),
        )
        first = cursor.fetchone()
        assert first is not None
        cursor.execute(
            """
            SELECT document_id, version_id, job_id
            FROM app.finalize_quarantine_upload(
              %s, 'member', %s, %s, %s, %s, %s,
              'text/plain', 'allowed', '2026-08-13', 'job-idem-1', 'Sample'
            )
            """,
            (user_id, auth_version, reservation_id, object_name, digest, len(content)),
        )
        second = cursor.fetchone()
        assert second == first

        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT dv.status
            FROM app.document_versions AS dv
            WHERE dv.id = %s
            """,
            (first[1],),
        )
        status_row = cursor.fetchone()
        assert status_row is not None
        assert status_row[0] == "uploaded"

        cursor.execute("SAVEPOINT wrong_user")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                SELECT document_id
                FROM app.finalize_quarantine_upload(
                  %s, 'member', %s, %s, %s, %s, %s,
                  'text/plain', 'allowed', '2026-08-13', 'job-idem-2', 'Sample'
                )
                """,
                (
                    other_id,
                    auth_version,
                    reservation_id,
                    object_name,
                    digest,
                    len(content),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT wrong_user")
        cursor.execute("RELEASE SAVEPOINT wrong_user")


def test_reserve_creates_uploading_version_before_finalize(
    db_connection: psycopg.Connection,
) -> None:
    """Quota reserve creates an observable ``uploading`` version before bytes land."""

    user_id = uuid.uuid4()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'member', true, true)
            """,
            (user_id,),
        )
        auth_version = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id, document_id, version_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, 512, 'upload-status', 'sess', NULL
            )
            """,
            (user_id, auth_version),
        )
        reserved = cursor.fetchone()
        assert reserved is not None
        reservation_id, document_id, version_id = reserved
        assert document_id is not None
        assert version_id is not None
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT status FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        status_row = cursor.fetchone()
        assert status_row is not None
        assert status_row[0] == "uploading"
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id, document_id, version_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, 512, 'upload-status', 'sess', NULL
            )
            """,
            (user_id, auth_version),
        )
        replay = cursor.fetchone()
        assert replay == (reservation_id, document_id, version_id)
