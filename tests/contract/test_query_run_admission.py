"""Contract tests for authenticated query-run admission and budgets."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr
from smart_rag_api.services.query_admission import admit_query_run_for_caller
from smart_rag_core.query_admission.ceilings import envelope_for_family
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import (
    QueryAdmissionResult,
    admit_query_run,
    consume_query_reservation,
    heartbeat_query_run,
    reconcile_expired_query_runs,
    record_run_restricted_evidence,
    true_up_query_reservation,
)
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.contract.integration_support import (
    REPO_ROOT,
    resolve_supabase_db_url,
    try_connect,
)


def _ensure_local_postgres() -> str:
    """Return a reachable local Supabase URL, starting the CLI stack if needed.

    Returns:
        Postgres URL on port 54322 when reachable.

    Raises:
        pytest.skip: When the stack cannot be started in this environment.
    """

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is not None:
        connection.close()
        return url

    import shutil
    import subprocess

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        pytest.skip("pnpm is unavailable; local Supabase contract not run")
    started = subprocess.run(  # noqa: S603 - pinned pnpm starts local CLI stack
        [pnpm, "exec", "supabase", "start"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if started.returncode != 0:
        pytest.skip(
            "local Supabase start failed: " + (started.stderr or started.stdout)[-500:]
        )
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.close()
    return url


@pytest.fixture
def db_url() -> str:
    """Yield the local Supabase URL or skip."""

    return _ensure_local_postgres()


@pytest.fixture
def db_connection(db_url: str) -> Iterator[psycopg.Connection]:
    """Yield one postgres-role connection with rollback on exit."""

    connection = psycopg.connect(db_url)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def _insert_user_profile(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    role: str,
    monthly_llm_budget_usd: Decimal | None = None,
) -> None:
    """Insert one Auth user and application profile."""

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
        INSERT INTO app.profiles (user_id, role, monthly_llm_budget_usd)
        VALUES (%s, %s::app.user_role, %s)
        """,
        (user_id, role, monthly_llm_budget_usd),
    )


def _insert_conversation(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    conversation_id: UUID | None = None,
) -> UUID:
    """Insert one undeleted conversation owned by ``user_id``."""

    conv_id = conversation_id or uuid4()
    cursor.execute(
        """
        INSERT INTO app.conversations (id, creator_user_id, title)
        VALUES (%s, %s, 'query admission fixture')
        """,
        (conv_id, user_id),
    )
    return conv_id


def _authorization_version(cursor: psycopg.Cursor) -> int:
    """Return the live company authorization version."""

    row = cursor.execute("SELECT app.current_authorization_version()").fetchone()
    assert row is not None
    return int(row[0])


def _caller(
    user_id: UUID,
    role: str,
    authorization_version: int,
    *,
    session_id: str | None = None,
    disabled: bool = False,
) -> CallerContext:
    """Build a server-shaped caller context for RPC tests."""

    return CallerContext(
        user_id=str(user_id),
        role=UserRole(role),
        authorization_version=authorization_version,
        session_id=session_id,
        disabled=disabled,
    )


def _admit(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    message: str = "what is the policy",
    route_family: Phase6RouteFamily = Phase6RouteFamily.HYBRID,
    idempotency_key: UUID | None = None,
    token_issued_at: datetime | None = None,
) -> tuple[QueryAdmissionResult, UUID]:
    """Admit one run as ``app_api`` and return the result plus key."""

    key = idempotency_key or uuid4()
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=route_family,
        message=message,
    )
    connection.execute("SET ROLE app_api")
    result = admit_query_run(
        connection,
        caller=caller,
        conversation_id=conversation_id,
        idempotency_key=key,
        payload_hash=payload_hash,
        route_family=route_family,
        token_issued_at=token_issued_at,
    )
    connection.execute("RESET ROLE")
    return result, key


# Public aliases for cross-module contract reuse (Pyright reportPrivateUsage).
admit = _admit
authorization_version = _authorization_version
caller_context = _caller
insert_conversation = _insert_conversation
insert_user_profile = _insert_user_profile


def _admit_error(
    connection: psycopg.Connection,
    match: str,
    **kwargs: object,
) -> None:
    """Expect a typed admission failure and roll back to a savepoint.

    Args:
        connection: Open test connection.
        match: Reason substring.
        **kwargs: Forwarded to ``_admit``.
    """

    connection.execute("SAVEPOINT admit_error")
    try:
        with pytest.raises(QueryAdmissionError, match=match):
            _admit(connection, **kwargs)  # pyright: ignore[reportArgumentType]
    finally:
        connection.execute("ROLLBACK TO SAVEPOINT admit_error")
        connection.execute("RESET ROLE")
        connection.execute("RELEASE SAVEPOINT admit_error")


def _retire_committed_query_run(
    db_url: str,
    *,
    run_id: UUID,
    reservation_id: UUID,
) -> None:
    """Close a committed fixture run so it cannot consume QT-CAP-004.

    Args:
        db_url: Local Postgres URL.
        run_id: Run inserted by a test that had to commit across connections.
        reservation_id: Matching ``query_run`` reservation.
    """

    with psycopg.connect(db_url) as connection:
        connection.execute(
            """
            UPDATE app.runs
            SET status = 'completed',
                completed_at = timezone('utc', now()),
                deadline_at = timezone('utc', now()) - interval '1 second'
            WHERE id = %s
            """,
            (run_id,),
        )
        connection.execute(
            """
            UPDATE app.budget_reservations
            SET status = 'released',
                committed_amount_usd = 0,
                remaining_usd = 0,
                released_at = timezone('utc', now())
            WHERE id = %s
            """,
            (reservation_id,),
        )
        connection.commit()


def test_sql_envelopes_match_python_table(db_connection: psycopg.Connection) -> None:
    """SQL ``query_route_envelope`` stays aligned with ``ceilings.py``."""

    with db_connection.cursor() as cursor:
        for family in Phase6RouteFamily:
            expected = envelope_for_family(family)
            row = cursor.execute(
                """
                SELECT deadline_seconds, model_call_ceiling, tool_ceiling,
                       envelope_usd, recursion_limit
                FROM app.query_route_envelope(%s)
                """,
                (family.value,),
            ).fetchone()
            assert row is not None
            assert int(row[0]) == expected.deadline_seconds
            assert int(row[1]) == expected.model_call_ceiling
            assert int(row[2]) == expected.tool_ceiling
            assert Decimal(str(row[3])) == expected.envelope_usd
            assert int(row[4]) == expected.recursion_limit


def test_admit_reconnects_same_key_and_rejects_payload_collision(
    db_connection: psycopg.Connection,
) -> None:
    """Same key+hash reconnects; same key+different hash fails closed."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    caller = _caller(user_id, "member", version)
    first, key = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="same",
    )
    second, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="same",
        idempotency_key=key,
    )
    assert first.reconnect is False
    assert second.reconnect is True
    assert second.context.run_id == first.context.run_id
    assert second.context.reservation_id == first.context.reservation_id

    _admit_error(
        db_connection,
        "key_collision",
        caller=caller,
        conversation_id=conversation_id,
        message="changed",
        idempotency_key=key,
    )

    with db_connection.cursor() as cursor:
        count = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.runs
            WHERE creator_user_id = %s AND conversation_id = %s
            """,
            (user_id, conversation_id),
        ).fetchone()
        reservations = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (user_id,),
        ).fetchone()
    assert count == (1,)
    assert reservations == (1,)


def test_concurrent_duplicate_admit_converges_on_one_run(
    db_url: str,
    db_connection: psycopg.Connection,
) -> None:
    """Two connections with the same key create one run and one reservation."""

    user_id = uuid4()
    key = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    db_connection.commit()
    caller = _caller(user_id, "member", version)
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="concurrent",
    )
    barrier = threading.Barrier(2)
    run_ids: list[UUID] = []
    reservation_ids: list[UUID] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        """Admit once from a dedicated connection after the barrier."""

        with psycopg.connect(db_url) as connection:
            connection.execute("SET ROLE app_api")
            barrier.wait(timeout=10)
            try:
                result = admit_query_run(
                    connection,
                    caller=caller,
                    conversation_id=conversation_id,
                    idempotency_key=key,
                    payload_hash=payload_hash,
                    route_family=Phase6RouteFamily.HYBRID,
                )
                connection.commit()
                with lock:
                    run_ids.append(result.context.run_id)
                    reservation_ids.append(result.context.reservation_id)
            except Exception as exc:
                connection.rollback()
                with lock:
                    errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert errors == []
    assert len(run_ids) == 2
    assert set(run_ids) == {run_ids[0]}
    assert set(reservation_ids) == {reservation_ids[0]}
    _retire_committed_query_run(
        db_url,
        run_id=run_ids[0],
        reservation_id=reservation_ids[0],
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


def test_direct_audit_and_usage_dml_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Runtime roles cannot insert/update/delete audit or usage rows."""

    with db_connection.cursor() as cursor:
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT audit_ins")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                """
                INSERT INTO app.audit_events (event_type, payload)
                VALUES ('forged', '{"passage":"secret"}'::jsonb)
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_ins")
        cursor.execute("SAVEPOINT usage_ins")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                """
                INSERT INTO app.llm_usage (
                  model_id, usage_kind, prompt_tokens, completion_tokens
                )
                VALUES ('x', 'answer', 1, 1)
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT usage_ins")
        cursor.execute("SAVEPOINT restricted_ins")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "INSERT INTO app.restricted_read_events (purpose) VALUES ('evidence')"
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_ins")
        cursor.execute("RESET ROLE")
        usage_id = cursor.execute(
            """
            INSERT INTO app.llm_usage (model_id, usage_kind)
            VALUES ('fixture', 'answer')
            RETURNING id
            """
        ).fetchone()
        assert usage_id is not None
        cursor.execute("SAVEPOINT usage_update")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute(
                "UPDATE app.llm_usage SET cost_usd = 9 WHERE id = %s",
                (usage_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT usage_update")
        cursor.execute("SAVEPOINT usage_delete")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute("DELETE FROM app.llm_usage WHERE id = %s", (usage_id[0],))
        cursor.execute("ROLLBACK TO SAVEPOINT usage_delete")
        audit_id = cursor.execute(
            """
            INSERT INTO app.audit_events (event_type)
            VALUES ('fixture')
            RETURNING id
            """
        ).fetchone()
        assert audit_id is not None
        cursor.execute("SAVEPOINT audit_update")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute(
                "UPDATE app.audit_events SET event_type = 'x' WHERE id = %s",
                (audit_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_update")
        cursor.execute("SAVEPOINT audit_delete")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute(
                "DELETE FROM app.audit_events WHERE id = %s",
                (audit_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_delete")


def test_restricted_run_evidence_is_chained_and_content_minimized(
    db_connection: psycopg.Connection,
) -> None:
    """Run-completion restricted evidence stores ids only, never passage text."""

    owner_id = uuid4()
    member_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=owner_id, role="owner")
        _insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=member_id)
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by, graph_eligible
            )
            VALUES (%s, 'Restricted run evidence', 'restricted', %s, false)
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
            "UPDATE app.documents SET current_version_id = %s WHERE id = %s",
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
        authz = _authorization_version(cursor)
    caller = _caller(member_id, "member", authz)
    admitted, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
    )
    with db_connection.cursor() as cursor:
        citation_id = cursor.execute(
            """
            INSERT INTO app.citations (run_id, citation_index, snippet, provenance)
            VALUES (%s, 0, 'should not be copied into audit', '{}'::jsonb)
            RETURNING id
            """,
            (admitted.context.run_id,),
        ).fetchone()
        assert citation_id is not None
    db_connection.execute("SET ROLE app_api")
    event_id = record_run_restricted_evidence(
        db_connection,
        caller=caller,
        run_id=admitted.context.run_id,
        document_id=document_id,
        version_id=version_id,
        session_id="session-run-evidence",
        citation_id=citation_id[0],
        purpose="evidence",
    )
    db_connection.execute("RESET ROLE")
    with db_connection.cursor() as cursor:
        row = cursor.execute(
            """
            SELECT
              restricted.purpose,
              restricted.run_id,
              restricted.citation_id,
              audit.payload,
              audit.event_type,
              audit.session_id
            FROM app.restricted_read_events AS restricted
            JOIN app.audit_events AS audit
              ON audit.id = restricted.audit_event_id
            WHERE restricted.id = %s
            """,
            (event_id,),
        ).fetchone()
        chain = cursor.execute("SELECT app.verify_audit_chain(1000)").fetchone()
    assert row is not None
    assert row[0] == "evidence"
    assert row[1] == admitted.context.run_id
    assert row[2] == citation_id[0]
    payload = row[3]
    assert payload["run_id"] == str(admitted.context.run_id)
    assert payload["citation_id"] == str(citation_id[0])
    assert payload["version_id"] == str(version_id)
    assert "should not be copied" not in str(payload)
    assert "passage" not in payload
    assert row[4] == "restricted_read.authorized"
    assert row[5] == "session-run-evidence"
    assert chain == (None,)


def test_fastapi_rate_limit_reject_creates_no_reservation(
    db_url: str,
    db_connection: psycopg.Connection,
) -> None:
    """429 and limiter-unavailable fail before cost; Valkey cannot authorize."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    db_connection.commit()
    caller = _caller(user_id, "member", version)
    with pytest.raises(QueryAdmissionError, match="limiter_unavailable"):
        admit_query_run_for_caller(
            db_url,
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=uuid4(),
            message="limited",
            route_family=Phase6RouteFamily.HYBRID,
            postgres_rate_limit_url=SecretStr("postgresql://x:y@127.0.0.1:1/none"),
        )
    with db_connection.cursor() as cursor:
        before = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (user_id,),
        ).fetchone()
    assert before == (0,)

    from smart_rag_api.services.auth_rate_limits import check_auth_rate_limit
    from smart_rag_api.services.query_admission import query_admission_bucket_key

    bucket = query_admission_bucket_key(str(user_id))
    postgres = SecretStr(db_url)
    for _ in range(20):
        check_auth_rate_limit(
            bucket_key=bucket,
            max_attempts=20,
            window_seconds=60,
            postgres_url=postgres,
        )
    with pytest.raises(QueryAdmissionError, match="rate_limited"):
        admit_query_run_for_caller(
            db_url,
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=uuid4(),
            message="limited",
            route_family=Phase6RouteFamily.HYBRID,
        )
    with db_connection.cursor() as cursor:
        after = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (user_id,),
        ).fetchone()
    assert after == (0,)

    other_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=other_id, role="member")
        other_conv = _insert_conversation(cursor, user_id=other_id)
        other_version = _authorization_version(cursor)
    db_connection.commit()
    other_caller = _caller(other_id, "member", other_version)
    result = admit_query_run_for_caller(
        db_url,
        caller=other_caller,
        conversation_id=other_conv,
        idempotency_key=uuid4(),
        message="ok-after-new-bucket-user",
        route_family=Phase6RouteFamily.HYBRID,
        postgres_rate_limit_url=SecretStr(db_url),
        valkey_limits_url=SecretStr("redis://valkey-is-not-authority"),
    )
    assert result.reconnect is False
    assert result.context.reserved_amount_usd == Decimal("2.80")
    assert result.context.role is UserRole.MEMBER
    _retire_committed_query_run(
        db_url,
        run_id=result.context.run_id,
        reservation_id=result.context.reservation_id,
    )
