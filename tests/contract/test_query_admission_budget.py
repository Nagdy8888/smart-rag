"""Reservation consume, crash true-up, heartbeat, and reconcile."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.service import (
    consume_query_reservation,
    heartbeat_query_run,
    reconcile_expired_query_runs,
    true_up_query_reservation,
)
from smart_rag_core.query_admission.usage import execute_counted_model_call

from tests.support.query_postgres import (
    admit as _admit,
)
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


def test_over_budget_and_concurrency_cap_reject_without_reservation(
    db_connection: psycopg.Connection,
) -> None:
    """Monthly cap and QT-CAP-004 fail closed before a sixth paid run."""

    poor_id = uuid4()
    busy_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(
            cursor,
            user_id=poor_id,
            role="member",
            monthly_llm_budget_usd=Decimal("0.01"),
        )
        _insert_user_profile(cursor, user_id=busy_id, role="member")
        poor_conv = _insert_conversation(cursor, user_id=poor_id)
        version = _authorization_version(cursor)

    _admit_error(
        db_connection,
        "budget_exhausted",
        caller=_caller(poor_id, "member", version),
        conversation_id=poor_conv,
    )

    busy = _caller(busy_id, "member", version)
    for index in range(5):
        with db_connection.cursor() as cursor:
            conv = _insert_conversation(cursor, user_id=busy_id)
        result, _ = _admit(
            db_connection,
            caller=busy,
            conversation_id=conv,
            message=f"run-{index}",
        )
        assert result.reconnect is False

    with db_connection.cursor() as cursor:
        sixth = _insert_conversation(cursor, user_id=busy_id)
    _admit_error(
        db_connection,
        "concurrency_cap",
        caller=busy,
        conversation_id=sixth,
        message="run-6",
    )

    with db_connection.cursor() as cursor:
        reservations = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (busy_id,),
        ).fetchone()
        poor_reservations = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (poor_id,),
        ).fetchone()
    assert reservations == (5,)
    assert poor_reservations == (0,)


def test_consume_optimistic_conflict_and_no_company_lock(
    db_connection: psycopg.Connection,
) -> None:
    """Stale version and oversize consume fail; SQL does not lock company rows."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
        source = cursor.execute(
            """
            SELECT pg_get_functiondef(p.oid)
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname = 'consume_query_reservation'
            """
        ).fetchone()
    assert source is not None
    body = str(source[0]).lower()
    assert "company_settings" not in body
    assert "for update" not in body

    caller = _caller(user_id, "member", version)
    admitted, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
    )
    db_connection.execute("SET ROLE app_api")
    first = consume_query_reservation(
        db_connection,
        caller=caller,
        reservation_id=admitted.context.reservation_id,
        expected_version=1,
        amount_usd=Decimal("0.40"),
        prompt_tokens=100,
        completion_tokens=50,
    )
    assert first.optimistic_version == 2
    db_connection.execute("SAVEPOINT consume_conflict")
    with pytest.raises(QueryBudgetError, match="optimistic_version_conflict"):
        consume_query_reservation(
            db_connection,
            caller=caller,
            reservation_id=admitted.context.reservation_id,
            expected_version=1,
            amount_usd=Decimal("0.40"),
            prompt_tokens=100,
            completion_tokens=50,
        )
    db_connection.execute("ROLLBACK TO SAVEPOINT consume_conflict")
    db_connection.execute("SAVEPOINT consume_exhaust")
    with pytest.raises(QueryBudgetError, match="reservation_exhausted"):
        consume_query_reservation(
            db_connection,
            caller=caller,
            reservation_id=admitted.context.reservation_id,
            expected_version=2,
            amount_usd=Decimal("99.00"),
            prompt_tokens=100,
            completion_tokens=50,
        )
    db_connection.execute("ROLLBACK TO SAVEPOINT consume_exhaust")
    db_connection.execute("RESET ROLE")


def test_crash_before_and_after_send_and_double_true_up(
    db_connection: psycopg.Connection,
) -> None:
    """Usage matches sent attempts; settlement is idempotent and cannot overspend."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        before_id = _insert_conversation(cursor, user_id=user_id)
        after_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    caller = _caller(user_id, "member", version)

    before, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=before_id,
        message="before",
    )
    db_connection.execute("SET ROLE app_api")
    with pytest.raises(RuntimeError, match="crash_before_send"):
        execute_counted_model_call(
            db_connection,
            caller=caller,
            run_id=before.context.run_id,
            reservation_id=before.context.reservation_id,
            expected_version=1,
            usage_kind="answer",
            model_id="mock-answer",
            provider_attempt_id=f"attempt-before-{uuid4()}",
            send=lambda: (_ for _ in ()).throw(RuntimeError("crash_before_send")),
        )
    settled_before = true_up_query_reservation(
        db_connection,
        caller=caller,
        reservation_id=before.context.reservation_id,
    )
    assert settled_before.status == "released"
    assert settled_before.committed_amount_usd == Decimal("0")

    after, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=after_id,
        message="after",
    )
    with pytest.raises(TimeoutAfterSendError):
        execute_counted_model_call(
            db_connection,
            caller=caller,
            run_id=after.context.run_id,
            reservation_id=after.context.reservation_id,
            expected_version=1,
            usage_kind="answer",
            model_id="mock-answer",
            provider_attempt_id=f"attempt-after-{uuid4()}",
            send=lambda: (_ for _ in ()).throw(TimeoutAfterSendError("lost")),
        )
    settled_after = true_up_query_reservation(
        db_connection,
        caller=caller,
        reservation_id=after.context.reservation_id,
    )
    assert settled_after.status == "committed"
    assert settled_after.committed_amount_usd == Decimal("0.40")
    assert settled_after.committed_amount_usd <= after.context.reserved_amount_usd
    second = true_up_query_reservation(
        db_connection,
        caller=caller,
        reservation_id=after.context.reservation_id,
    )
    assert second.already_settled is True
    assert second.committed_amount_usd == settled_after.committed_amount_usd

    usage = db_connection.execute(
        """
        SELECT timeout_after_send, cost_usd, usage_kind
        FROM app.llm_usage
        WHERE run_id = %s
        """,
        (after.context.run_id,),
    ).fetchone()
    db_connection.execute("RESET ROLE")
    # RESET may lose visibility; re-read as postgres.
    with db_connection.cursor() as cursor:
        usage = cursor.execute(
            """
            SELECT timeout_after_send, cost_usd, usage_kind, prompt_tokens
            FROM app.llm_usage
            WHERE run_id = %s
            """,
            (after.context.run_id,),
        ).fetchone()
        before_usage = cursor.execute(
            "SELECT count(*)::integer FROM app.llm_usage WHERE run_id = %s",
            (before.context.run_id,),
        ).fetchone()
    assert before_usage == (0,)
    assert usage is not None
    assert usage[0] is True
    assert Decimal(str(usage[1])) == Decimal("0.40")
    assert usage[2] == "answer"


def test_cross_user_consume_and_heartbeat_deadline(
    db_connection: psycopg.Connection,
) -> None:
    """Foreign run consume fails; heartbeat after deadline fails closed."""

    alice = uuid4()
    bob = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=alice, role="member")
        _insert_user_profile(cursor, user_id=bob, role="member")
        alice_conv = _insert_conversation(cursor, user_id=alice)
        version = _authorization_version(cursor)
    alice_caller = _caller(alice, "member", version)
    bob_caller = _caller(bob, "member", version)
    admitted, _ = _admit(
        db_connection,
        caller=alice_caller,
        conversation_id=alice_conv,
    )
    db_connection.execute("SET ROLE app_api")
    db_connection.execute("SAVEPOINT bob_consume")
    with pytest.raises(QueryAdmissionError, match="run_forbidden"):
        consume_query_reservation(
            db_connection,
            caller=bob_caller,
            reservation_id=admitted.context.reservation_id,
            expected_version=1,
            amount_usd=Decimal("0.40"),
            prompt_tokens=10,
            completion_tokens=10,
        )
    db_connection.execute("ROLLBACK TO SAVEPOINT bob_consume")
    beat = heartbeat_query_run(
        db_connection,
        caller=alice_caller,
        run_id=admitted.context.run_id,
    )
    assert beat is not None
    db_connection.execute("RESET ROLE")
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.runs
            SET deadline_at = timezone('utc', now()) - interval '1 second'
            WHERE id = %s
            """,
            (admitted.context.run_id,),
        )
    db_connection.execute("SET ROLE app_api")
    db_connection.execute("SAVEPOINT hb_deadline")
    with pytest.raises(QueryAdmissionError, match="deadline_exhausted"):
        heartbeat_query_run(
            db_connection,
            caller=alice_caller,
            run_id=admitted.context.run_id,
        )
    db_connection.execute("ROLLBACK TO SAVEPOINT hb_deadline")
    db_connection.execute("RESET ROLE")


def test_reconcile_true_up_after_expiry(db_connection: psycopg.Connection) -> None:
    """Expiry reconciler settles unused reservations without overspend."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    caller = _caller(user_id, "member", version)
    admitted, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
    )
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.runs
            SET deadline_at = timezone('utc', now()) - interval '1 second',
                heartbeat_at = timezone('utc', now()) - interval '3 minutes'
            WHERE id = %s
            """,
            (admitted.context.run_id,),
        )
        cursor.execute(
            """
            UPDATE app.budget_reservations
            SET expires_at = timezone('utc', now()) - interval '1 second'
            WHERE id = %s
            """,
            (admitted.context.reservation_id,),
        )
    db_connection.execute("SET ROLE app_worker")
    settled = reconcile_expired_query_runs(db_connection)
    db_connection.execute("RESET ROLE")
    assert settled >= 1
    with db_connection.cursor() as cursor:
        run_status = cursor.execute(
            "SELECT status::text FROM app.runs WHERE id = %s",
            (admitted.context.run_id,),
        ).fetchone()
        reservation = cursor.execute(
            """
            SELECT status::text, committed_amount_usd
            FROM app.budget_reservations
            WHERE id = %s
            """,
            (admitted.context.reservation_id,),
        ).fetchone()
    assert run_status == ("partial",)
    assert reservation is not None
    assert reservation[0] in {"released", "committed"}
    assert Decimal(str(reservation[1] or 0)) == Decimal("0")
