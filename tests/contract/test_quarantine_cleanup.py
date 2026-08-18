"""Quarantine cleanup candidate and retry-safety contract tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row for cleanup tests."""

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


def test_list_never_finalized_and_over_limit_candidates(
    db_connection: psycopg.Connection,
) -> None:
    """Cleanup lists never-finalized (>TTL) and over-limit reservations."""

    user_id = uuid.uuid4()
    stale_id = uuid.uuid4()
    over_id = uuid.uuid4()
    as_of = datetime.now(tz=UTC)

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
            UPDATE app.company_settings
            SET quarantine_ttl_hours = 24
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        cursor.execute(
            """
            INSERT INTO app.upload_quota_reservations (
              id, user_id, reserved_bytes, status, expires_at,
              storage_bucket, storage_path, created_at
            )
            VALUES (
              %s, %s, 100, 'reserved',
              %s - interval '1 hour',
              'documents-quarantine',
              %s,
              %s - interval '25 hours'
            )
            """,
            (
                stale_id,
                user_id,
                as_of,
                f"{user_id}/{stale_id}/old.pdf",
                as_of,
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.upload_quota_reservations (
              id, user_id, reserved_bytes, status, expires_at,
              storage_bucket, storage_path, actual_bytes, finalized_at,
              committed_at, cleanup_status
            )
            VALUES (
              %s, %s, 100, 'committed',
              %s + interval '1 hour',
              'documents-quarantine',
              %s,
              5000,
              %s,
              %s,
              'pending'
            )
            """,
            (
                over_id,
                user_id,
                as_of,
                f"{user_id}/{over_id}/big.pdf",
                as_of,
                as_of,
            ),
        )

        cursor.execute("SET ROLE app_worker")
        cursor.execute(
            """
            SELECT reservation_id, reason
            FROM app.list_quarantine_cleanup_candidates(%s, 50)
            """,
            (as_of,),
        )
        rows = {row[0]: row[1] for row in cursor.fetchall()}
        assert stale_id in rows
        assert rows[stale_id] == "never_finalized"
        assert over_id in rows
        assert rows[over_id] == "over_limit"

        cursor.execute(
            "SELECT app.release_expired_upload_reservations(%s)",
            (as_of,),
        )
        first_release_row = cursor.fetchone()
        assert first_release_row is not None
        first_release = first_release_row[0]
        cursor.execute(
            "SELECT app.release_expired_upload_reservations(%s)",
            (as_of,),
        )
        second_release_row = cursor.fetchone()
        assert second_release_row is not None
        second_release = second_release_row[0]
        assert first_release >= 1
        assert second_release == 0  # idempotent

        cursor.execute("SELECT app.mark_quarantine_cleanup_done(%s)", (over_id,))
        cursor.execute("SELECT app.mark_quarantine_cleanup_done(%s)", (over_id,))
        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT cleanup_status, status
            FROM app.upload_quota_reservations WHERE id = %s
            """,
            (over_id,),
        )
        done = cursor.fetchone()
        assert done is not None
        assert done[0] == "done"
        assert done[1] == "released"


def test_expired_quota_deletes_uploading_version(
    db_connection: psycopg.Connection,
) -> None:
    """Never-finalized 24h/expiry cleanup removes the uploading version shell."""

    user_id = uuid.uuid4()
    as_of = datetime.now(tz=UTC)
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'member', true, true)
            """,
            (user_id,),
        )
        cursor.execute("SELECT app.current_authorization_version()")
        auth_row = cursor.fetchone()
        assert auth_row is not None
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id, document_id, version_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, 100, 'expire-upload', 'sess', NULL
            )
            """,
            (user_id, int(auth_row[0])),
        )
        reserved = cursor.fetchone()
        assert reserved is not None
        reservation_id, document_id, version_id = reserved
        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            UPDATE app.upload_quota_reservations
            SET expires_at = %s - interval '1 minute'
            WHERE id = %s
            """,
            (as_of, reservation_id),
        )
        cursor.execute("SET ROLE app_worker")
        cursor.execute("SELECT app.release_expired_upload_reservations(%s)", (as_of,))
        released = cursor.fetchone()
        assert released is not None
        assert released[0] >= 1
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT count(*) FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        versions = cursor.fetchone()
        assert versions is not None
        assert versions[0] == 0
        cursor.execute(
            "SELECT count(*) FROM app.documents WHERE id = %s",
            (document_id,),
        )
        documents = cursor.fetchone()
        assert documents is not None
        assert documents[0] == 0


def test_cleanup_uses_storage_api_not_sql_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """process_cleanup_candidate must call Storage HTTP delete helper."""

    from smart_rag_api.services import quarantine_cleanup as qc
    from smart_rag_api.services.quarantine_cleanup import (
        CleanupCandidate,
        process_cleanup_candidate,
    )

    calls: list[tuple[str, str]] = []

    def _fake_delete(settings: object, *, bucket: str, object_path: str) -> None:
        """Record one Storage deletion without performing network I/O.

        Args:
            settings: Unused Storage administration settings.
            bucket: Restricted Storage bucket name.
            object_path: Object path selected for cleanup.
        """

        calls.append((bucket, object_path))

    monkeypatch.setattr(qc, "delete_object", _fake_delete)

    # Avoid real DB: patch mark path by short-circuiting psycopg.connect
    class _Conn:
        """Minimal context-managed connection used after Storage deletion."""

        def __enter__(self) -> _Conn:
            """Return the fake connection for the cleanup context."""

            return self

        def __exit__(self, *args: object) -> None:
            """Leave the fake connection without suppressing exceptions.

            Args:
                *args: Context-manager exception details, if any.
            """

            return None

        def execute(self, *args: object, **kwargs: object) -> None:
            """Accept the cleanup completion statement without persistence.

            Args:
                *args: Positional query arguments.
                **kwargs: Keyword query arguments.
            """

            return None

        def commit(self) -> None:
            """Accept the completion commit without persistence."""

            return None

    def _fake_connect(*args: object, **kwargs: object) -> _Conn:
        """Return a fake connection for any psycopg connection arguments.

        Args:
            *args: Ignored positional connection arguments.
            **kwargs: Ignored keyword connection arguments.

        Returns:
            Context-managed fake connection.
        """

        del args, kwargs
        return _Conn()

    monkeypatch.setattr(qc.psycopg, "connect", _fake_connect)

    candidate = CleanupCandidate(
        reservation_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        storage_bucket="documents-quarantine",
        storage_path="user/res/file.pdf",
        reserved_bytes=10,
        actual_bytes=10,
        cleanup_status="pending",
        reason="over_limit",
    )
    settings = MagicMock()
    process_cleanup_candidate("postgresql://invalid", settings, candidate)
    assert calls == [("documents-quarantine", "user/res/file.pdf")]


def test_scan_events_block_fake_clean_for_app_api(
    db_connection: psycopg.Connection,
) -> None:
    """Phase 2 cannot represent scans as clean via app_api; app_worker can."""

    with db_connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_worker")
        cursor.execute(
            """
            INSERT INTO app.document_scan_events (result, object_hash)
            VALUES ('clean', 'worker-rls-clean')
            RETURNING id
            """
        )
        worker_clean = cursor.fetchone()
        assert worker_clean is not None
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT fake_clean")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                INSERT INTO app.document_scan_events (result, object_hash)
                VALUES ('clean', 'abc')
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT fake_clean")
        cursor.execute("RELEASE SAVEPOINT fake_clean")
        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            INSERT INTO app.document_scan_events (result, object_hash)
            VALUES ('unscannable', 'def')
            RETURNING id
            """
        )
        assert cursor.fetchone() is not None
        cursor.execute("SAVEPOINT scan_update")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                UPDATE app.document_scan_events
                SET details = '{}'::jsonb
                WHERE object_hash = 'def'
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT scan_update")
        cursor.execute("RELEASE SAVEPOINT scan_update")
