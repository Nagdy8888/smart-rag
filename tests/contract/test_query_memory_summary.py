"""Conversation summary accounting against reserved envelopes."""

from __future__ import annotations

from uuid import uuid4

import psycopg
from smart_rag_core.memory.summary import (
    SUMMARY_DEFERRED,
    SUMMARY_WRITTEN,
    maybe_generate_conversation_summary,
)

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


def test_summary_defers_when_envelope_cannot_afford_it(
    db_connection: psycopg.Connection,
) -> None:
    """Unbudgeted summary does not consume a model call."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    admitted, _ = _admit(db_connection, caller=caller, conversation_id=conversation_id)
    outcome = maybe_generate_conversation_summary(
        db_connection,
        caller=caller,
        run_id=admitted.context.run_id,
        reservation_id=admitted.context.reservation_id,
        expected_version=admitted.context.optimistic_version,
        remaining_model_calls=0,
        remaining_usd=admitted.context.remaining_usd,
        conversation_id=conversation_id,
        user_id=str(user_id),
        memory_records=(),
    )
    assert outcome.status == SUMMARY_DEFERRED
    assert outcome.usage_id is None


def test_summary_counts_as_model_call(
    db_connection: psycopg.Connection,
) -> None:
    """Affordable summary consume uses usage_kind=summary."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    admitted, _ = _admit(db_connection, caller=caller, conversation_id=conversation_id)
    stored: list[tuple[tuple[str, str, str], str, dict[str, object]]] = []

    def _put(
        namespace: tuple[str, str, str],
        key: str,
        payload: dict[str, object],
    ) -> None:
        """Record one store write for later assertions.

        Args:
            namespace: Store namespace tuple.
            key: Item key.
            payload: JSON-compatible value.
        """

        stored.append((namespace, key, payload))

    db_connection.execute("SET ROLE app_api")
    outcome = maybe_generate_conversation_summary(
        db_connection,
        caller=caller,
        run_id=admitted.context.run_id,
        reservation_id=admitted.context.reservation_id,
        expected_version=admitted.context.optimistic_version,
        remaining_model_calls=admitted.context.model_call_ceiling,
        remaining_usd=admitted.context.remaining_usd,
        conversation_id=conversation_id,
        user_id=str(user_id),
        memory_records=(),
        store_put=_put,
    )
    db_connection.execute("RESET ROLE")
    assert outcome.status == SUMMARY_WRITTEN
    assert outcome.usage_id is not None
    assert stored
    assert "passage" not in stored[0][2]
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT usage_kind FROM app.llm_usage WHERE id = %s",
            (outcome.usage_id,),
        )
        kind = cursor.fetchone()
    assert kind == ("summary",)
