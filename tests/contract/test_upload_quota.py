"""Upload quota reservation/finalize contract tests (Phase 2 Packet 5)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from tests.contract.integration_support import require_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row for quota tests."""

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


def test_reserve_finalize_idempotent_and_over_limit(
    db_connection: psycopg.Connection,
) -> None:
    """Reserve is idempotent; finalize marks over-limit for cleanup."""

    user_id = uuid.uuid4()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (
              user_id, role, upload_enabled, mfa_enrolled, upload_quota_bytes
            )
            VALUES (%s, 'member', true, true, 10000)
            """,
            (user_id,),
        )
        cursor.execute(
            """
            UPDATE app.company_settings
            SET quarantine_byte_cap = 1000000,
                upload_quota_bytes = 1000000
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        auth_version = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")

        cursor.execute(
            """
            SELECT reservation_id, reserved_bytes, expires_at
            FROM app.reserve_upload_quota(
              %s, 'member', %s, 1000, 'idem-1', 'sess-1', NULL
            )
            """,
            (user_id, auth_version),
        )
        first = cursor.fetchone()
        assert first is not None
        reservation_id = first[0]
        assert first[1] == 1000
        expires_at = first[2]
        assert expires_at <= datetime.now(tz=UTC) + timedelta(minutes=16)

        cursor.execute(
            """
            SELECT reservation_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, 1000, 'idem-1', 'sess-1', NULL
            )
            """,
            (user_id, auth_version),
        )
        second = cursor.fetchone()
        assert second is not None
        assert second[0] == reservation_id

        cursor.execute(
            """
            SELECT status, cleanup_status, over_limit, recorded_actual_bytes
            FROM app.finalize_upload_quota(%s, 'member', %s, %s, 5000)
            """,
            (user_id, auth_version, reservation_id),
        )
        finalized = cursor.fetchone()
        assert finalized is not None
        assert finalized[0] == "committed"
        assert finalized[1] == "pending"
        assert finalized[2] is True
        assert finalized[3] == 5000

        # Idempotent finalize replay
        cursor.execute(
            """
            SELECT recorded_actual_bytes, over_limit
            FROM app.finalize_upload_quota(%s, 'member', %s, %s, 9999)
            """,
            (user_id, auth_version, reservation_id),
        )
        replay = cursor.fetchone()
        assert replay is not None
        assert replay[0] == 5000


def test_reserve_rejects_quota_and_allows_member_without_mfa(
    db_connection: psycopg.Connection,
) -> None:
    """Per-user cap still fails closed; MFA enrollment is not an upload gate."""

    capped = uuid.uuid4()
    no_mfa = uuid.uuid4()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, capped, f"{capped}@example.com")
        _insert_auth_user(cursor, no_mfa, f"{no_mfa}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (
              user_id, role, upload_enabled, mfa_enrolled, upload_quota_bytes
            )
            VALUES
              (%s, 'member', true, true, 500),
              (%s, 'member', true, false, 10000)
            """,
            (capped, no_mfa),
        )
        auth_version = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT over_quota")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                SELECT * FROM app.reserve_upload_quota(
                  %s, 'member', %s, 1000, 'over', 's', NULL
                )
                """,
                (capped, auth_version),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT over_quota")
        cursor.execute("RELEASE SAVEPOINT over_quota")
        cursor.execute(
            """
            SELECT reservation_id FROM app.reserve_upload_quota(
              %s, 'member', %s, 100, 'nomfa', 's', NULL
            )
            """,
            (no_mfa, auth_version),
        )
        allowed = cursor.fetchone()
        assert allowed is not None


def test_effective_capability_lifetime_label() -> None:
    """Effective capability is min(reservation, JWT exp); 15m does not revoke JWT."""

    from smart_rag_api.services.upload_quota import UploadReservation

    reservation_exp = datetime(2026, 8, 13, 12, 15, tzinfo=UTC)
    jwt_exp = datetime(2026, 8, 13, 13, 0, tzinfo=UTC)
    reservation = UploadReservation(
        reservation_id=uuid.uuid4(),
        expires_at=reservation_exp,
        reserved_bytes=100,
        storage_bucket="documents-quarantine",
        storage_path="u/r/",
        access_token_exp=jwt_exp,
    )
    assert reservation.effective_capability_expires_at == reservation_exp

    short_jwt = UploadReservation(
        reservation_id=uuid.uuid4(),
        expires_at=reservation_exp,
        reserved_bytes=100,
        storage_bucket="documents-quarantine",
        storage_path="u/r/",
        access_token_exp=datetime(2026, 8, 13, 12, 5, tzinfo=UTC),
    )
    assert short_jwt.effective_capability_expires_at == short_jwt.access_token_exp
