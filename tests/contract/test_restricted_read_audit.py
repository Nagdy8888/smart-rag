"""Restricted evidence, preview, and download audit contracts."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg import sql

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one local Supabase connection or skip when unavailable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def _insert_user_profile(
    cursor: psycopg.Cursor,
    *,
    user_id: uuid.UUID,
    role: str,
) -> None:
    """Insert one minimal Auth user and active application profile."""

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
        """,
        (user_id, f"{user_id}@example.com"),
    )
    cursor.execute(
        """
        INSERT INTO app.profiles (user_id, role)
        VALUES (%s, %s::app.user_role)
        """,
        (user_id, role),
    )


def _authorization_version(cursor: psycopg.Cursor) -> int:
    """Return the live company authorization version."""

    row = cursor.execute("SELECT app.current_authorization_version()").fetchone()
    assert row is not None
    return int(row[0])


def _authorize_read(
    cursor: psycopg.Cursor,
    *,
    user_id: uuid.UUID,
    role: str,
    authorization_version: int,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    purpose: str,
    session_id: str,
    signed_url_expires_at: datetime | None = None,
) -> uuid.UUID:
    """Invoke the typed restricted-read admission RPC."""

    row = cursor.execute(
        """
        SELECT app.authorize_restricted_read(
          %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            user_id,
            role,
            authorization_version,
            document_id,
            version_id,
            purpose,
            session_id,
            signed_url_expires_at,
        ),
    ).fetchone()
    assert row is not None
    return uuid.UUID(str(row[0]))


def test_restricted_read_surfaces_append_content_free_chain_events(
    db_connection: psycopg.Connection,
) -> None:
    """Authorized surfaces append linked events with purpose and no evidence text."""

    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    outsider_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=owner_id, role="owner")
        _insert_user_profile(cursor, user_id=member_id, role="member")
        _insert_user_profile(cursor, user_id=outsider_id, role="viewer")
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by, graph_eligible
            )
            VALUES (%s, 'Restricted audit fixture', 'restricted', %s, false)
            """,
            (document_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by
            )
            VALUES (%s, %s, 1, %s)
            """,
            (version_id, document_id, owner_id),
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
            INSERT INTO app.document_acl (
              document_id, grantee_user_id, granted_by
            )
            VALUES (%s, %s, %s)
            """,
            (document_id, member_id, owner_id),
        )
        authorization_version = _authorization_version(cursor)

        cursor.execute("SET ROLE app_api")
        evidence_id = _authorize_read(
            cursor,
            user_id=member_id,
            role="member",
            authorization_version=authorization_version,
            document_id=document_id,
            version_id=version_id,
            purpose="evidence",
            session_id="session-evidence",
        )
        preview_id = _authorize_read(
            cursor,
            user_id=member_id,
            role="member",
            authorization_version=authorization_version,
            document_id=document_id,
            version_id=version_id,
            purpose="preview",
            session_id="session-preview",
        )
        download_expiry = datetime.now(tz=UTC) + timedelta(minutes=5)
        download_id = _authorize_read(
            cursor,
            user_id=member_id,
            role="member",
            authorization_version=authorization_version,
            document_id=document_id,
            version_id=version_id,
            purpose="download",
            session_id="session-download",
            signed_url_expires_at=download_expiry,
        )
        cursor.execute("RESET ROLE")

        event_rows = cursor.execute(
            """
            SELECT
              restricted.id,
              restricted.purpose,
              restricted.signed_url_expires_at,
              audit.event_type,
              audit.purpose,
              audit.resource_type,
              audit.resource_id,
              audit.session_id,
              audit.payload,
              audit.event_hash
            FROM app.restricted_read_events AS restricted
            JOIN app.audit_events AS audit
              ON audit.id = restricted.audit_event_id
            WHERE restricted.id = ANY(%s)
            ORDER BY restricted.purpose
            """,
            ([evidence_id, preview_id, download_id],),
        ).fetchall()
        assert len(event_rows) == 3
        assert {str(row[1]) for row in event_rows} == {
            "download",
            "evidence",
            "preview",
        }
        for row in event_rows:
            purpose = str(row[1])
            assert row[3] == "restricted_read.authorized"
            assert row[4] == purpose
            assert row[5] == "document_version"
            assert row[6] == version_id
            assert str(row[7]).startswith("session-")
            assert row[8] == {
                "access_surface": purpose,
                "version_id": str(version_id),
            }
            assert len(str(row[9])) == 64
            if purpose == "download":
                assert row[2] == download_expiry
            else:
                assert row[2] is None

        chain_result = cursor.execute("SELECT app.verify_audit_chain(1000)").fetchone()
        assert chain_result == (None,)


def test_restricted_read_denials_leave_no_audit_record(
    db_connection: psycopg.Connection,
) -> None:
    """ACL, context, current-version, purpose, and expiry failures are atomic."""

    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    outsider_id = uuid.uuid4()
    document_id = uuid.uuid4()
    current_version_id = uuid.uuid4()
    stale_version_id = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=owner_id, role="owner")
        _insert_user_profile(cursor, user_id=member_id, role="member")
        _insert_user_profile(cursor, user_id=outsider_id, role="member")
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by, graph_eligible
            )
            VALUES (%s, 'Restricted denial fixture', 'restricted', %s, false)
            """,
            (document_id, owner_id),
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
            (
                stale_version_id,
                document_id,
                owner_id,
                current_version_id,
                document_id,
                owner_id,
            ),
        )
        cursor.execute(
            "UPDATE app.documents SET current_version_id = %s WHERE id = %s",
            (current_version_id, document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_acl (
              document_id, grantee_user_id, granted_by
            )
            VALUES (%s, %s, %s)
            """,
            (document_id, member_id, owner_id),
        )
        authorization_version = _authorization_version(cursor)
        baseline_row = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.audit_events
            WHERE target_id = %s
              AND event_type = 'restricted_read.authorized'
            """,
            (document_id,),
        ).fetchone()
        assert baseline_row is not None
        baseline = int(baseline_row[0])

        cursor.execute("SET ROLE app_api")
        denied_calls = [
            (
                outsider_id,
                "member",
                authorization_version,
                current_version_id,
                "evidence",
                "denied-outsider",
                None,
            ),
            (
                member_id,
                "admin",
                authorization_version,
                current_version_id,
                "evidence",
                "denied-forged-role",
                None,
            ),
            (
                member_id,
                "member",
                authorization_version - 1,
                current_version_id,
                "evidence",
                "denied-stale-context",
                None,
            ),
            (
                member_id,
                "member",
                authorization_version,
                stale_version_id,
                "preview",
                "denied-stale-version",
                None,
            ),
            (
                member_id,
                "member",
                authorization_version,
                current_version_id,
                "raw-text",
                "denied-purpose",
                None,
            ),
            (
                member_id,
                "member",
                authorization_version,
                current_version_id,
                "download",
                "denied-expiry",
                datetime.now(tz=UTC) - timedelta(seconds=1),
            ),
        ]
        for index, call in enumerate(denied_calls):
            savepoint = sql.Identifier(f"denied_{index}")
            cursor.execute(sql.SQL("SAVEPOINT {}").format(savepoint))
            with pytest.raises(psycopg.errors.RaiseException):
                cursor.execute(
                    """
                    SELECT app.authorize_restricted_read(
                      %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        call[0],
                        call[1],
                        call[2],
                        document_id,
                        call[3],
                        call[4],
                        call[5],
                        call[6],
                    ),
                )
            cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(savepoint))
            cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(savepoint))
        cursor.execute("RESET ROLE")

        final_row = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.audit_events
            WHERE target_id = %s
              AND event_type = 'restricted_read.authorized'
            """,
            (document_id,),
        ).fetchone()
        assert final_row == (baseline,)


def test_restricted_read_event_rows_are_immutable(
    db_connection: psycopg.Connection,
) -> None:
    """Even privileged direct UPDATE/DELETE is blocked by append-only triggers."""

    with db_connection.cursor() as cursor:
        event_id = cursor.execute(
            """
            INSERT INTO app.restricted_read_events (purpose)
            VALUES ('test-fixture')
            RETURNING id
            """
        ).fetchone()
        assert event_id is not None

        cursor.execute("SAVEPOINT restricted_update")
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="append-only",
        ):
            cursor.execute(
                """
                UPDATE app.restricted_read_events
                SET purpose = 'mutated'
                WHERE id = %s
                """,
                (event_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_update")
        cursor.execute("RELEASE SAVEPOINT restricted_update")

        cursor.execute("SAVEPOINT restricted_delete")
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="append-only",
        ):
            cursor.execute(
                "DELETE FROM app.restricted_read_events WHERE id = %s",
                (event_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_delete")
        cursor.execute("RELEASE SAVEPOINT restricted_delete")
