"""Query-run checkpoint and event reaping contracts."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import psycopg
from smart_rag_core.memory.reaper import (
    reap_query_run_retention,
)
from smart_rag_core.query_admission.service import true_up_query_reservation

from tests.support.query_memory import _NOW, _complete_run
from tests.support.query_postgres import (
    admit as _admit,
)
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


def test_reaper_nulls_completed_keys_at_seven_days(
    db_connection: psycopg.Connection,
) -> None:
    """Completed keys at the 7-day boundary are NULLed; 6d23h keys remain."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    old, old_key = _admit(db_connection, caller=caller, conversation_id=conversation_id)
    fresh, fresh_key = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="second",
    )
    with db_connection.cursor() as cursor:
        _complete_run(cursor, old.context.run_id, completed_at=_NOW - timedelta(days=7))
        _complete_run(
            cursor,
            fresh.context.run_id,
            completed_at=_NOW - timedelta(days=6, hours=23),
        )
        cursor.execute(
            """
            INSERT INTO app.run_events (run_id, sequence, event_type)
            VALUES (%s, 1, 'status'), (%s, 1, 'status')
            """,
            (old.context.run_id, fresh.context.run_id),
        )
    result = reap_query_run_retention(db_connection, now=_NOW)
    assert result.true_up_invoked is False
    assert result.keys_nulled == 1
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT idempotency_key, idempotency_key_hash FROM app.runs WHERE id = %s",
            (old.context.run_id,),
        )
        nulled = cursor.fetchone()
        cursor.execute(
            "SELECT idempotency_key FROM app.runs WHERE id = %s",
            (fresh.context.run_id,),
        )
        kept = cursor.fetchone()
    assert nulled is not None
    assert nulled[0] is None
    assert nulled[1] is not None
    assert kept is not None
    assert kept[0] == str(fresh_key)
    del old_key


def test_reaper_does_not_touch_pending_keys(
    db_connection: psycopg.Connection,
) -> None:
    """Pending/running keys are never NULLed even when older than seven days."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    admitted, key = _admit(
        db_connection, caller=caller, conversation_id=conversation_id
    )
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.runs
            SET updated_at = %s, created_at = %s
            WHERE id = %s
            """,
            (
                _NOW - timedelta(days=10),
                _NOW - timedelta(days=10),
                admitted.context.run_id,
            ),
        )
    result = reap_query_run_retention(db_connection, now=_NOW)
    assert result.pending_keys_preserved >= 1
    assert result.true_up_invoked is False
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT idempotency_key, status FROM app.runs WHERE id = %s",
            (admitted.context.run_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == str(key)
    assert str(row[1]) == "pending"


def test_reaper_does_not_call_budget_true_up(
    db_connection: psycopg.Connection,
) -> None:
    """GC is independent of reservation settlement."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    admitted, _ = _admit(db_connection, caller=caller, conversation_id=conversation_id)
    reservation_id = admitted.context.reservation_id
    remaining_before = admitted.context.remaining_usd
    with db_connection.cursor() as cursor:
        _complete_run(
            cursor, admitted.context.run_id, completed_at=_NOW - timedelta(days=8)
        )
        cursor.execute(
            "SELECT remaining_usd, status FROM app.budget_reservations WHERE id = %s",
            (reservation_id,),
        )
        before = cursor.fetchone()
    result = reap_query_run_retention(db_connection, now=_NOW)
    assert result.true_up_invoked is False
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT remaining_usd, status FROM app.budget_reservations WHERE id = %s",
            (reservation_id,),
        )
        after = cursor.fetchone()
    assert before == after
    assert remaining_before == admitted.context.remaining_usd
    db_connection.execute("SET ROLE app_api")
    settled = true_up_query_reservation(
        db_connection,
        caller=caller,
        reservation_id=reservation_id,
    )
    db_connection.execute("RESET ROLE")
    assert settled.reservation_id == reservation_id


def test_reaped_key_still_reconnects_same_paid_run(
    db_connection: psycopg.Connection,
) -> None:
    """After key NULL, the same client key cannot create a second paid admit."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    first, key = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="same payload",
    )
    with db_connection.cursor() as cursor:
        _complete_run(
            cursor, first.context.run_id, completed_at=_NOW - timedelta(days=7)
        )
    reap_query_run_retention(db_connection, now=_NOW)
    second, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="same payload",
        idempotency_key=key,
    )
    assert second.reconnect is True
    assert second.context.run_id == first.context.run_id
    third, new_key = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="different payload needs a new key",
        idempotency_key=uuid4(),
    )
    assert third.reconnect is False
    assert third.context.run_id != first.context.run_id
    del new_key


def test_events_reaped_after_thirty_days(
    db_connection: psycopg.Connection,
) -> None:
    """Completed run_events older than 30 days are deleted; 29-day events remain."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    old, _ = _admit(db_connection, caller=caller, conversation_id=conversation_id)
    young, _ = _admit(
        db_connection, caller=caller, conversation_id=conversation_id, message="young"
    )
    with db_connection.cursor() as cursor:
        _complete_run(
            cursor, old.context.run_id, completed_at=_NOW - timedelta(days=30)
        )
        _complete_run(
            cursor, young.context.run_id, completed_at=_NOW - timedelta(days=29)
        )
        cursor.execute(
            """
            INSERT INTO app.run_events (run_id, sequence, event_type)
            VALUES (%s, 1, 'status'), (%s, 1, 'status')
            """,
            (old.context.run_id, young.context.run_id),
        )
    result = reap_query_run_retention(db_connection, now=_NOW)
    assert result.events_deleted == 1
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM app.run_events WHERE run_id = %s",
            (old.context.run_id,),
        )
        old_count = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM app.run_events WHERE run_id = %s",
            (young.context.run_id,),
        )
        young_count = cursor.fetchone()
    assert old_count == (0,)
    assert young_count == (1,)
