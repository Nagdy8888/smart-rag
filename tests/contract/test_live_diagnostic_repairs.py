"""Real PostgreSQL regressions found by the single live diagnostic campaign."""

from __future__ import annotations

import re
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from smart_rag_core.sse.catalog import ALLOWED_SSE_EVENT_TYPES

from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    ensure_local_postgres,
    insert_conversation,
    insert_user_profile,
)


@pytest.fixture
def connection() -> Iterator[psycopg.Connection]:
    """Use an explicit local database and roll back all test mutations."""
    with psycopg.connect(ensure_local_postgres()) as db:
        with db.transaction(force_rollback=True):
            yield db


def test_database_event_catalog_matches_application(
    connection: psycopg.Connection,
) -> None:
    """Every application event survives persistence; unknown event types stay denied."""
    row = connection.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid='app.run_events'::regclass AND conname='run_events_type_allowed'"
    ).fetchone()
    assert row is not None
    assert set(re.findall(r"'([a-z_]+)'", row[0])) == ALLOWED_SSE_EVENT_TYPES


@pytest.mark.parametrize("extra_terms", [None, ["construct_actor_critic_graph"], [""]])
def test_term_rpc_accepts_bound_text_without_evaluating_nul(
    connection: psycopg.Connection, extra_terms: list[str] | None
) -> None:
    """Valid term input executes under the API role, even when it has no hits."""
    user = uuid4()
    with connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=user, role="owner")
        version = authorization_version(cursor)
    connection.execute("SET LOCAL ROLE app_api")
    rows = connection.execute(
        "SELECT * FROM app.retrieve_term_candidates(%s,'owner',%s,%s,5,NULL,%s)",
        (user, version, "zxqdiagnostic" + uuid4().hex, extra_terms),
    ).fetchall()
    assert len(rows) <= 5


def test_term_rpc_keeps_invalid_callers_and_nul_input_out(
    connection: psycopg.Connection,
) -> None:
    """Removing an invalid NUL expression neither grants access nor admits NUL text."""
    with connection.cursor() as cursor:
        version = authorization_version(cursor)
    connection.execute("SET LOCAL ROLE app_api")
    assert (
        connection.execute(
            "SELECT * FROM app.retrieve_term_candidates(%s,'owner',%s,'policy',5,NULL,NULL)",
            (uuid4(), version),
        ).fetchall()
        == []
    )
    with pytest.raises(psycopg.DataError), connection.transaction():
        connection.execute("SELECT %s::text", ("invalid\x00input",))


def test_term_rpc_privileges_remain_api_only(connection: psycopg.Connection) -> None:
    """Anonymous, direct authenticated and worker roles gain no retrieval RPC grant."""
    signature = (
        "app.retrieve_term_candidates(uuid,text,bigint,text,integer,text,text[])"
    )
    for role in ("anon", "authenticated", "app_worker"):
        row = connection.execute(
            "SELECT has_function_privilege(%s,%s,'EXECUTE')", (role, signature)
        ).fetchone()
        assert row == (False,)


@pytest.mark.parametrize(
    "event_type,payload",
    [
        ("answer_origin", {"origin": "web"}),
        ("tool_progress", {"tool_key": "web_search", "phase": "started"}),
    ],
)
def test_origin_and_progress_events_persist_and_replay(
    connection: psycopg.Connection, event_type: str, payload: dict[str, str]
) -> None:
    """Existing origin/progress contracts pass the same authorized append RPC."""
    user = uuid4()
    with connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=user, role="owner")
        conversation = insert_conversation(cursor, user_id=user)
        version = authorization_version(cursor)
    caller = caller_context(user, "owner", version)
    result, _ = admit(connection, caller=caller, conversation_id=conversation)
    connection.execute("SET LOCAL ROLE app_api")
    row = connection.execute(
        "SELECT event_type,payload FROM app.append_run_event(%s,'owner',%s,%s,%s,%s)",
        (user, version, result.context.run_id, event_type, Jsonb(payload)),
    ).fetchone()
    assert row == (event_type, payload)
    with pytest.raises(psycopg.Error), connection.transaction():
        connection.execute(
            "SELECT * FROM app.append_run_event(%s,'owner',%s,%s,%s,%s)",
            (uuid4(), version, result.context.run_id, event_type, Jsonb(payload)),
        )
