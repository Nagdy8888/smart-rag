"""Invitation create/accept/replay contract tests (Phase 2 Packet 4)."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect

INVITATION_WINDOW_HOURS = 24


def _token_hash(raw: str) -> str:
    """Hash one raw invitation token for database comparison.

    Args:
        raw: Unhashed single-use invitation token.

    Returns:
        Lowercase SHA-256 hexadecimal digest.
    """

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal Auth user needed by invitation foreign keys.

    Args:
        cursor: Open test transaction cursor.
        user_id: Stable test user identifier.
        email: Test user email address.
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
        invitation_row = cursor.fetchone()
        assert invitation_row is not None
        invitation_id = invitation_row[0]

        cursor.execute("SET ROLE app_api")
        cursor.execute(
            "SELECT app.accept_invitation(%s, %s, %s)",
            (digest, invitee, email),
        )
        first_row = cursor.fetchone()
        assert first_row is not None
        first = first_row[0]
        assert first == invitation_id

        cursor.execute(
            "SELECT app.accept_invitation(%s, %s, %s)",
            (digest, invitee, email),
        )
        second_row = cursor.fetchone()
        assert second_row is not None
        second = second_row[0]
        assert second == invitation_id

        with pytest.raises(psycopg.errors.RaiseException, match="already accepted"):
            cursor.execute(
                "SELECT app.accept_invitation(%s, %s, %s)",
                (digest, other, email),
            )


def test_accept_invitation_does_not_demote_owner(
    db_connection: psycopg.Connection,
) -> None:
    """A member invitation cannot overwrite an existing owner profile."""

    owner_id = uuid.uuid4()
    email = f"owner-keep-{owner_id}@example.com"
    digest = _token_hash("member-invite-would-demote")
    expires_at = datetime.now(tz=UTC) + timedelta(hours=INVITATION_WINDOW_HOURS)

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, owner_id, email)
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled)
            VALUES (%s, 'owner'::app.user_role, true)
            """,
            (owner_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.team_invitations (
              email, role, token_hash, expires_at, upload_enabled
            )
            VALUES (%s, 'member', %s, %s, false)
            """,
            (email, digest, expires_at),
        )
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT member_demote")
        with pytest.raises(psycopg.errors.RaiseException, match="would demote"):
            cursor.execute(
                "SELECT app.accept_invitation(%s, %s, %s, %s)",
                (digest, owner_id, email, "aal2"),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT member_demote")
        cursor.execute("RELEASE SAVEPOINT member_demote")
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT role::text, upload_enabled FROM app.profiles WHERE user_id = %s",
            (owner_id,),
        )
        row = cursor.fetchone()
    assert row == ("owner", True)


def test_accept_invitation_privileged_upgrade_succeeds_at_aal1(
    db_connection: psycopg.Connection,
) -> None:
    """Member-to-admin upgrades succeed at ordinary assurance and revoke sessions."""

    user_id = uuid.uuid4()
    email = f"upgrade-{user_id}@example.com"
    digest = _token_hash("admin-upgrade-token")
    expires_at = datetime.now(tz=UTC) + timedelta(hours=INVITATION_WINDOW_HOURS)

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, email)
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled)
            VALUES (%s, 'member'::app.user_role, false)
            """,
            (user_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.team_invitations (
              email, role, token_hash, expires_at, upload_enabled
            )
            VALUES (%s, 'admin', %s, %s, true)
            RETURNING id
            """,
            (email, digest, expires_at),
        )
        invitation_row = cursor.fetchone()
        assert invitation_row is not None
        invitation_id = invitation_row[0]
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            "SELECT app.accept_invitation(%s, %s, %s, %s)",
            (digest, user_id, email, "aal1"),
        )
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT role::text, upload_enabled FROM app.profiles WHERE user_id = %s",
            (user_id,),
        )
        profile = cursor.fetchone()
        cursor.execute(
            """
            SELECT session_id
            FROM app.revoked_sessions
            WHERE user_id = %s
              AND session_id = %s
            """,
            (user_id, f"invitation-accept:{invitation_id}"),
        )
        revoked = cursor.fetchone()
    assert profile == ("admin", True)
    assert revoked is not None


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
    """First bootstrap succeeds only when no owner exists; a second call is false.

    The Phase 9 candidate seed already has an owner referenced by
    ``glossary_imports`` and documents, so deleting owners is not possible
    without destroying seed foreign keys. When an owner already exists this
    test proves bootstrap cannot create a second owner. The empty-database
    first-success path still runs after a local reset.
    """

    owner = uuid.uuid4()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, owner, f"owner-{owner}@example.com")
        cursor.execute(
            "SELECT count(*) FROM app.profiles WHERE role = 'owner'::app.user_role"
        )
        existing = cursor.fetchone()
        assert existing is not None
        owner_count = int(existing[0])
        cursor.execute("SET ROLE app_api")
        if owner_count == 0:
            cursor.execute("SELECT app.bootstrap_owner(%s)", (owner,))
            first_bootstrap = cursor.fetchone()
            assert first_bootstrap is not None
            assert first_bootstrap[0] is True
            cursor.execute("SELECT app.bootstrap_owner(%s)", (uuid.uuid4(),))
            second_bootstrap = cursor.fetchone()
            assert second_bootstrap is not None
            assert second_bootstrap[0] is False
            return
        cursor.execute("SELECT app.bootstrap_owner(%s)", (owner,))
        blocked = cursor.fetchone()
        assert blocked is not None
        assert blocked[0] is False
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT count(*) FROM app.profiles WHERE role = 'owner'::app.user_role"
        )
        after = cursor.fetchone()
        assert after is not None
        assert int(after[0]) == owner_count
