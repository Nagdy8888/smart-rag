"""Two-session run-row lock behavior for SSE persist."""

from __future__ import annotations

import time
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.sse.store import EVENT_STORE_LOCK_TIMEOUT, PostgresRunEventStore

from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    ensure_local_postgres,
    insert_conversation,
    insert_user_profile,
    retire_committed_query_run,
)
from tests.unit.typed_attrs import typed_attr


@pytest.fixture
def db_url() -> str:
    """Reuse the local Supabase helper from query-run admission tests.

    Returns:
        Postgres URL when local Supabase is reachable.
    """

    return ensure_local_postgres()


def test_event_store_transaction_applies_lock_timeout(db_url: str) -> None:
    """Each store transaction sets a two-second lock timeout after ``app_api``."""

    store = PostgresRunEventStore(db_url)
    try:
        with typed_attr(store, "_transaction")() as connection:
            shown = connection.execute("SHOW lock_timeout").fetchone()
            assert shown is not None
            assert str(shown[0]) in {EVENT_STORE_LOCK_TIMEOUT, "00:00:02"}
            role = connection.execute("SELECT current_user").fetchone()
            assert role is not None
            assert str(role[0]) == "app_api"
    finally:
        store.close()


def test_event_store_role_is_transaction_scoped(db_url: str) -> None:
    """``app_api`` ends with the store transaction on the reused session."""

    store = PostgresRunEventStore(db_url)
    try:
        with typed_attr(store, "_transaction")() as connection:
            inside_pid = connection.info.backend_pid
        pool = typed_attr(store, "_pool")
        reused = pool.acquire()
        try:
            assert reused.info.backend_pid == inside_pid
            role = reused.execute("SELECT current_user").fetchone()
            assert role is not None
            assert str(role[0]) != "app_api"
            reused.rollback()
        finally:
            pool.release(reused, reusable=True)
    finally:
        store.close()


def test_uncommitted_usage_blocks_append_until_lock_timeout(db_url: str) -> None:
    """Uncommitted ``llm_usage`` makes heartbeat append fail in two seconds.

    This is the c31e50dc deadlock class: the graph session holds KEY SHARE
    on ``app.runs`` while ``append_run_event`` needs ``FOR UPDATE``.
    """

    owner = uuid4()
    holder = psycopg.connect(db_url)
    holder.autocommit = False
    store = PostgresRunEventStore(db_url)
    run_id = None
    reservation_id = None
    try:
        cursor = holder.cursor()
        insert_user_profile(cursor, user_id=owner, role="owner")
        conversation_id = insert_conversation(cursor, user_id=owner)
        version = authorization_version(cursor)
        caller = caller_context(owner, "owner", version)
        result, _key = admit(
            holder,
            caller=caller,
            conversation_id=conversation_id,
            route_family=Phase6RouteFamily.COMPOSITE,
        )
        holder.commit()
        run_id = result.context.run_id
        reservation_id = result.context.reservation_id
        holder.execute("SET ROLE app_api")
        execute_counted_model_call(
            holder,
            caller=caller,
            run_id=run_id,
            reservation_id=reservation_id,
            expected_version=result.context.optimistic_version,
            usage_kind="answer",
            model_id="mock-answer",
            provider_attempt_id=f"attempt-lock-{uuid4()}",
            send=lambda: "ok",
        )
        started = time.perf_counter()
        with pytest.raises(QueryAdmissionError) as exc:
            store.append(caller, run_id=run_id, event_type="heartbeat", payload={})
        elapsed = time.perf_counter() - started
        assert exc.value.reason == "lock_timeout"
        assert 1.0 <= elapsed < 8.0
        holder.rollback()
        persisted = store.append(
            caller, run_id=run_id, event_type="heartbeat", payload={}
        )
        assert persisted.event_type == "heartbeat"
        assert persisted.sequence >= 1
    finally:
        store.close()
        holder.rollback()
        holder.close()
        if run_id is not None and reservation_id is not None:
            retire_committed_query_run(
                db_url,
                run_id=run_id,
                reservation_id=reservation_id,
            )
