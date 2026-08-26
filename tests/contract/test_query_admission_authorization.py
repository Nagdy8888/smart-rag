"""Unauthorized admission paths create no paid run."""

from __future__ import annotations

from uuid import uuid4

import psycopg

from tests.support.query_postgres import admit_error as _admit_error
from tests.support.query_postgres import (
    authorization_version as _authorization_version,
)
from tests.support.query_postgres import (
    caller_context as _caller,
)
from tests.support.query_postgres import (
    insert_conversation as _insert_conversation,
)
from tests.support.query_postgres import (
    insert_user_profile as _insert_user_profile,
)


def test_unauthorized_paths_create_no_paid_run(
    db_connection: psycopg.Connection,
) -> None:
    """Disabled, stale-role, stale-version, foreign, and deleted all fail closed."""

    owner_id = uuid4()
    member_id = uuid4()
    other_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=owner_id, role="owner")
        _insert_user_profile(cursor, user_id=member_id, role="member")
        _insert_user_profile(cursor, user_id=other_id, role="member")
        owned = _insert_conversation(cursor, user_id=member_id)
        foreign = _insert_conversation(cursor, user_id=other_id)
        deleted = _insert_conversation(cursor, user_id=member_id)
        cursor.execute(
            "UPDATE app.conversations SET deleted_at = timezone('utc', now()) WHERE id = %s",
            (deleted,),
        )
        stale_version = _authorization_version(cursor)
        cursor.execute(
            """
            UPDATE app.company_settings
            SET authorization_version = authorization_version + 1
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        cursor.execute(
            "UPDATE app.profiles SET disabled_at = timezone('utc', now()) WHERE user_id = %s",
            (owner_id,),
        )
        version = _authorization_version(cursor)
        cursor.execute(
            """
            INSERT INTO app.revoked_sessions (session_id, user_id)
            VALUES (%s, %s)
            """,
            ("revoked-session", member_id),
        )

    member = _caller(member_id, "member", version)
    with db_connection.cursor() as cursor:
        owner_conv = _insert_conversation(cursor, user_id=owner_id)
    _admit_error(
        db_connection,
        "authorization_rejected",
        caller=_caller(owner_id, "owner", version),
        conversation_id=owner_conv,
    )
    _admit_error(
        db_connection,
        "authorization_rejected",
        caller=_caller(member_id, "admin", version),
        conversation_id=owned,
    )
    _admit_error(
        db_connection,
        "authorization_rejected",
        caller=_caller(member_id, "member", stale_version),
        conversation_id=owned,
    )
    _admit_error(
        db_connection,
        "session_revoked",
        caller=_caller(member_id, "member", version, session_id="revoked-session"),
        conversation_id=owned,
    )
    _admit_error(
        db_connection,
        "conversation_forbidden",
        caller=member,
        conversation_id=foreign,
    )
    _admit_error(
        db_connection,
        "conversation_deleted",
        caller=member,
        conversation_id=deleted,
    )

    with db_connection.cursor() as cursor:
        paid = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE reservation_kind = 'query_run'
              AND user_id = ANY(%s)
            """,
            ([owner_id, member_id, other_id],),
        ).fetchone()
        runs = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.runs
            WHERE creator_user_id = ANY(%s)
            """,
            ([owner_id, member_id, other_id],),
        ).fetchone()
    assert paid == (0,)
    assert runs == (0,)
