"""Invitation create/accept/replay contract tests (Phase 2 Packet 4)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect

INVITATION_WINDOW_HOURS = 24


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
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


def test_accept_invitation_idempotent_and_rejects_replay(
    db_connection: psycopg.Connection,
) -> None:
    """Accept succeeds once; second user or replay raises."""

    invitee = uuid.uuid4()
    other = uuid.uuid4()
    email = f"invite-{invitee}@example.com"
    raw_token = "test-invite-token-raw"  # noqa: S105 - fixture digest input only
    digest = _token_hash(raw_token)
    expires_at = datetime.now(tz=UTC) + timedelta(hours=INVITATION_WINDOW_HOURS)

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, invitee, email)
        _insert_auth_user(cursor, other, f"other-{other}@example.com")
        cursor.execute(
            """
            INSERT INTO app.team_invitations (
              email, role, token_hash, expires_at, upload_enabled
            )
            VALUES (%s, 'member', %s, %s, true)
            RETURNING id
            """,
            (email, digest, expires_at),
        )
        invitation_id = cursor.fetchone()[0]

        cursor.execute("SET ROLE app_api")
        cursor.execute(
            "SELECT app.accept_invitation(%s, %s, %s)",
            (digest, invitee, email),
        )
        first = cursor.fetchone()[0]
        assert first == invitation_id

        cursor.execute(
            "SELECT app.accept_invitation(%s, %s, %s)",
            (digest, invitee, email),
        )
        second = cursor.fetchone()[0]
        assert second == invitation_id

        with pytest.raises(psycopg.errors.RaiseException, match="already accepted"):
            cursor.execute(
                "SELECT app.accept_invitation(%s, %s, %s)",
                (digest, other, email),
            )


def test_expired_invitation_rejected(db_connection: psycopg.Connection) -> None:
    """Expired invitations fail closed."""

    invitee = uuid.uuid4()
    email = f"expired-{invitee}@example.com"
    digest = _token_hash("expired-token")
    expired_at = datetime.now(tz=UTC) - timedelta(minutes=5)

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, invitee, email)
        cursor.execute(
            """
            INSERT INTO app.team_invitations (
              email, role, token_hash, expires_at
            )
            VALUES (%s, 'viewer', %s, %s)
            """,
            (email, digest, expired_at),
        )
        cursor.execute("SET ROLE app_api")
        with pytest.raises(psycopg.errors.RaiseException, match="expired"):
            cursor.execute(
                "SELECT app.accept_invitation(%s, %s, %s)",
                (digest, invitee, email),
            )


def test_bootstrap_owner_race_safe_once(db_connection: psycopg.Connection) -> None:
    """First bootstrap succeeds; second call returns false."""

    owner = uuid.uuid4()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, owner, f"owner-{owner}@example.com")
        cursor.execute("DELETE FROM app.profiles WHERE role = 'owner'::app.user_role")
        cursor.execute("SET ROLE app_api")
        cursor.execute("SELECT app.bootstrap_owner(%s)", (owner,))
        assert cursor.fetchone()[0] is True
        cursor.execute("SELECT app.bootstrap_owner(%s)", (uuid.uuid4(),))
        assert cursor.fetchone()[0] is False
