"""Reproduce the recorded reservation/run lock cycle without provider calls."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import psycopg

from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    ensure_local_postgres,
    insert_conversation,
    insert_user_profile,
)


def test_cancel_does_not_hold_run_while_waiting_for_reservation() -> None:
    """A verifier holding consumed budget can acquire its run during cancellation."""
    url = ensure_local_postgres()
    user = uuid4()
    with psycopg.connect(url) as setup:
        with setup.cursor() as cursor:
            insert_user_profile(cursor, user_id=user, role="owner")
            conversation = insert_conversation(cursor, user_id=user)
            version = authorization_version(cursor)
        result, _ = admit(
            setup,
            caller=caller_context(user, "owner", version),
            conversation_id=conversation,
        )
    context = result.context
    started = Event()
    pids: list[int] = []

    def cancel() -> str:
        """Run the actual creator-authorized RPC on a separate transaction."""
        with psycopg.connect(url) as db:
            pids.append(db.info.backend_pid)
            db.execute("SET LOCAL lock_timeout='5s'")
            db.execute("SET LOCAL ROLE app_api")
            started.set()
            row = db.execute(
                "SELECT status::text FROM app.cancel_query_run(%s,'owner',%s,%s)",
                (user, version, context.run_id),
            ).fetchone()
            assert row is not None
            return str(row[0])

    with psycopg.connect(url) as holder, ThreadPoolExecutor(max_workers=1) as pool:
        holder.execute(
            "SELECT id FROM app.budget_reservations WHERE id=%s FOR UPDATE",
            (context.reservation_id,),
        )
        future = pool.submit(cancel)
        try:
            assert started.wait(2)
            with psycopg.connect(url, autocommit=True) as observer:
                until = time.monotonic() + 3
                while time.monotonic() < until:
                    row = observer.execute(
                        "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                        (pids[0],),
                    ).fetchone()
                    if row == ("Lock",):
                        break
                    time.sleep(0.01)
                else:
                    raise AssertionError("Cancel did not reach its reservation lock")
            holder.execute("SET LOCAL lock_timeout='300ms'")
            holder.execute(
                "SELECT id FROM app.runs WHERE id=%s FOR UPDATE", (context.run_id,)
            )
        finally:
            holder.rollback()
        assert future.result(timeout=6) == "cancelled"
