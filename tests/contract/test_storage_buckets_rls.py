"""Private Storage bucket and RLS contract tests (Phase 2 Packet 5)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row for Storage RLS tests."""

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
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_all_smart_rag_buckets_are_private(db_connection: psycopg.Connection) -> None:
    """Every Packet 5 bucket must exist with public=false."""

    expected = {
        "documents-quarantine",
        "documents-originals",
        "web-snapshots",
        "table-artifacts",
        "exports",
    }
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, public
            FROM storage.buckets
            WHERE id = ANY(%s)
            """,
            (list(expected),),
        )
        rows = {row[0]: row[1] for row in cursor.fetchall()}
    assert set(rows) == expected
    assert all(public is False for public in rows.values())


def test_quarantine_insert_own_path_allowed_cross_user_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Authenticated INSERT allowed only under own active reservation path."""

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    reservation_id = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_a, f"{user_a}@example.com")
        _insert_auth_user(cursor, user_b, f"{user_b}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (
              user_id, role, upload_enabled, mfa_enrolled
            )
            VALUES
              (%s, 'member', true, true),
              (%s, 'member', true, true)
            """,
            (user_a, user_b),
        )
        cursor.execute(
            """
            INSERT INTO app.upload_quota_reservations (
              id, user_id, reserved_bytes, status, expires_at,
              storage_bucket, storage_path
            )
            VALUES (
              %s, %s, 1024, 'reserved',
              timezone('utc', now()) + interval '15 minutes',
              'documents-quarantine',
              %s
            )
            """,
            (
                reservation_id,
                user_a,
                f"{user_a}/{reservation_id}/",
            ),
        )

        own_path = f"{user_a}/{reservation_id}/report.pdf"
        cursor.execute(
            "SELECT set_config('request.jwt.claim.sub', %s, true)", (str(user_a),)
        )
        cursor.execute("SET LOCAL ROLE authenticated")
        cursor.execute(
            """
            INSERT INTO storage.objects (bucket_id, name, owner, owner_id)
            VALUES ('documents-quarantine', %s, %s, %s)
            """,
            (own_path, user_a, str(user_a)),
        )

        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT set_config('request.jwt.claim.sub', %s, true)", (str(user_b),)
        )
        cursor.execute("SET LOCAL ROLE authenticated")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                INSERT INTO storage.objects (bucket_id, name, owner, owner_id)
                VALUES ('documents-quarantine', %s, %s, %s)
                """,
                (own_path, user_b, str(user_b)),
            )


def test_quarantine_select_list_denied_and_wrong_bucket_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Quarantine is non-browseable; authenticated cannot insert into originals."""

    user_id = uuid.uuid4()
    reservation_id = uuid.uuid4()
    object_name = f"{user_id}/{reservation_id}/secret.pdf"

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'member', true, true)
            """,
            (user_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.upload_quota_reservations (
              id, user_id, reserved_bytes, status, expires_at, storage_path
            )
            VALUES (
              %s, %s, 2048, 'reserved',
              timezone('utc', now()) + interval '15 minutes',
              %s
            )
            """,
            (reservation_id, user_id, f"{user_id}/{reservation_id}/"),
        )

        # Insert as postgres (bypass) to seed an object for SELECT denial.
        cursor.execute(
            """
            INSERT INTO storage.objects (bucket_id, name, owner, owner_id)
            VALUES ('documents-quarantine', %s, %s, %s)
            """,
            (object_name, user_id, str(user_id)),
        )

        cursor.execute(
            "SELECT set_config('request.jwt.claim.sub', %s, true)",
            (str(user_id),),
        )
        cursor.execute("SET LOCAL ROLE authenticated")
        cursor.execute(
            """
            SELECT count(*) FROM storage.objects
            WHERE bucket_id = 'documents-quarantine'
            """
        )
        visible_quarantine_objects = cursor.fetchone()
        assert visible_quarantine_objects is not None
        assert visible_quarantine_objects[0] == 0

        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                INSERT INTO storage.objects (bucket_id, name, owner, owner_id)
                VALUES ('documents-originals', %s, %s, %s)
                """,
                (
                    f"documents/{user_id}/versions/{uuid.uuid4()}/a.pdf",
                    user_id,
                    str(user_id),
                ),
            )


def test_shared_settings_reject_storage_admin_secret() -> None:
    """Runtime Shared/Backend/Worker settings must not load Storage Admin secret."""

    from smart_rag_api.main import live, ready
    from smart_rag_core.settings import (
        BackendSettings,
        SharedSettings,
        WorkerSettings,
        load_settings,
    )

    shared_fields = SharedSettings.model_fields
    backend_fields = BackendSettings.model_fields
    assert "supabase_storage_admin_secret" not in shared_fields
    assert "supabase_storage_admin_secret" not in backend_fields
    assert "supabase_storage_admin_secret" not in WorkerSettings.model_fields

    health = {**live(), **ready()}
    assert "storage_admin" not in str(health).lower()
    assert "SUPABASE_STORAGE_ADMIN_SECRET" not in str(health)

    loaded = load_settings(BackendSettings)
    dumped = loaded.model_dump_json()
    assert "SUPABASE_STORAGE_ADMIN_SECRET" not in dumped
