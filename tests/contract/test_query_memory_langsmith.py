"""LangSmith deletion retry and feedback-tag retention."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.feedback.tags import FEEDBACK_TAGS
from smart_rag_core.observability.langsmith_deletion import (
    RecordingLangSmithDeletionTransport,
    process_langsmith_deletion_requests,
)

from tests.support.query_memory import QUERY_MEMORY_NOW
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


def test_langsmith_deletion_request_retries_within_sla(
    db_connection: psycopg.Connection,
) -> None:
    """Durable LangSmith requests retry; SLA expiry does not claim cloud delete."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
        cursor.execute(
            """
            INSERT INTO app.langsmith_deletion_requests (
              conversation_id_hash,
              hashed_trace_keys,
              status,
              sla_deadline_at,
              retry_at
            )
            VALUES (
              encode(sha256(convert_to(%s, 'UTF8')), 'hex'),
              ARRAY['abc123'],
              'pending',
              %s,
              %s
            )
            """,
            (
                str(conversation_id),
                QUERY_MEMORY_NOW + timedelta(hours=24),
                QUERY_MEMORY_NOW,
            ),
        )
    transport = RecordingLangSmithDeletionTransport(fail_times=1)
    recorded, retried, expired = process_langsmith_deletion_requests(
        db_connection, transport=transport, now=QUERY_MEMORY_NOW
    )
    assert recorded == 0
    assert retried >= 1
    assert expired == 0
    recorded, retried, expired = process_langsmith_deletion_requests(
        db_connection, transport=transport, now=QUERY_MEMORY_NOW + timedelta(minutes=2)
    )
    assert recorded >= 1
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.langsmith_deletion_requests (
              conversation_id_hash,
              hashed_trace_keys,
              status,
              sla_deadline_at,
              retry_at
            )
            VALUES ('deadbeef', ARRAY['def456'], 'pending', %s, %s)
            """,
            (
                QUERY_MEMORY_NOW - timedelta(hours=1),
                QUERY_MEMORY_NOW + timedelta(hours=25),
            ),
        )
    late = RecordingLangSmithDeletionTransport()
    recorded, retried, expired = process_langsmith_deletion_requests(
        db_connection, transport=late, now=QUERY_MEMORY_NOW + timedelta(hours=25)
    )
    assert expired >= 1
    assert ("def456",) not in late.calls
    del authz
    del user_id


def test_feedback_tag_required_and_unmerged(
    db_connection: psycopg.Connection,
) -> None:
    """Feedback RPC requires one exact catalog tag."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    admitted, _ = _admit(db_connection, caller=caller, conversation_id=conversation_id)
    db_connection.execute("SET ROLE app_api")
    with db_connection.cursor() as cursor:
        with pytest.raises(psycopg.Error, match="invalid_tag"):
            with db_connection.transaction():
                cursor.execute(
                    """
                    SELECT app.submit_run_feedback(
                      %s::uuid,
                      %s::text,
                      %s::bigint,
                      %s::uuid,
                      1::smallint,
                      'note'::text,
                      'merged-tag'::text
                    )
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        admitted.context.run_id,
                    ),
                )
        cursor.execute(
            """
            SELECT app.submit_run_feedback(
              %s::uuid,
              %s::text,
              %s::bigint,
              %s::uuid,
              5::smallint,
              'note'::text,
              %s::text
            )
            """,
            (
                caller.user_id,
                caller.rpc_role(),
                caller.rpc_authorization_version(),
                admitted.context.run_id,
                next(iter(FEEDBACK_TAGS)),
            ),
        )
        row = cursor.fetchone()
    db_connection.execute("RESET ROLE")
    assert row is not None
