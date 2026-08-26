"""Conversation deletion lingering-id and cross-user denial."""

from __future__ import annotations

import threading
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.conversations import delete_conversation, get_conversation
from smart_rag_core.memory.reaper import (
    search_conversation_lingering_ids,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

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


def test_delete_leaves_no_lingering_conversation_ids(
    db_connection: psycopg.Connection,
) -> None:
    """Immediate deletion tombstones then purges application/checkpoint/store state."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    admitted, _ = _admit(db_connection, caller=caller, conversation_id=conversation_id)
    thread_id = str(conversation_id)
    prefix = f"company.{user_id}.{conversation_id}"
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.messages (conversation_id, role, content)
            VALUES (%s, 'user', 'secret source text must not linger')
            """,
            (conversation_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.run_events (run_id, sequence, event_type)
            VALUES (%s, 1, 'status')
            """,
            (admitted.context.run_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.citations (run_id, citation_index, snippet, provenance)
            VALUES (%s, 0, 'passage copy', '{}'::jsonb)
            """,
            (admitted.context.run_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.user_feedback (run_id, user_id, rating, comment, tag)
            VALUES (%s, %s, 1, 'private note', 'bad citation')
            """,
            (admitted.context.run_id, user_id),
        )
        cursor.execute(
            """
            INSERT INTO langgraph.checkpoints (
              thread_id, checkpoint_ns, checkpoint_id, checkpoint
            )
            VALUES (%s, '', 'ckpt-1', '{}'::jsonb)
            """,
            (thread_id,),
        )
        cursor.execute(
            """
            INSERT INTO langgraph.checkpoint_blobs (
              thread_id, checkpoint_ns, channel, version, type, blob
            )
            VALUES (%s, '', 'state', '1', 'json', '\\x00'::bytea)
            """,
            (thread_id,),
        )
        cursor.execute(
            """
            INSERT INTO langgraph.checkpoint_writes (
              thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, blob
            )
            VALUES (%s, '', 'ckpt-1', 'task', 0, 'state', '\\x00'::bytea)
            """,
            (thread_id,),
        )
        cursor.execute(
            """
            INSERT INTO langgraph.store (prefix, key, value)
            VALUES (%s, 'summary', '{"summary":"compact"}'::jsonb)
            """,
            (prefix,),
        )
    db_connection.execute("SET ROLE app_api")
    delete_conversation(db_connection, caller=caller, conversation_id=conversation_id)
    db_connection.execute("RESET ROLE")
    lingering = search_conversation_lingering_ids(
        db_connection, conversation_id=conversation_id
    )
    assert lingering
    assert all(count == 0 for count in lingering.values())
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT deleted_at FROM app.conversations WHERE id = %s",
            (conversation_id,),
        )
        tombstone = cursor.fetchone()
        cursor.execute(
            """
            SELECT payload
            FROM app.audit_events
            WHERE event_type = 'conversation_deleted'
              AND target_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        )
        audit = cursor.fetchone()
        cursor.execute(
            """
            SELECT hashed_trace_keys, status
            FROM app.langsmith_deletion_requests
            WHERE conversation_id_hash = encode(sha256(convert_to(%s, 'UTF8')), 'hex')
            """,
            (thread_id,),
        )
        request = cursor.fetchone()
    assert tombstone is not None
    assert tombstone[0] is not None
    assert audit is not None
    payload = audit[0]
    assert "secret source text" not in str(payload)
    assert "private note" not in str(payload)
    assert request is not None
    assert request[1] == "pending"
    db_connection.execute("SET ROLE app_api")
    with pytest.raises(QueryAdmissionError, match="not_found"):
        get_conversation(db_connection, caller=caller, conversation_id=conversation_id)
    db_connection.execute("RESET ROLE")


def test_foreign_delete_is_not_found(db_connection: psycopg.Connection) -> None:
    """Non-owners cannot delete another user's conversation."""

    owner_id = uuid4()
    other_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=owner_id, role="member")
        _insert_user_profile(cursor, user_id=other_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=owner_id)
        authz = _authorization_version(cursor)
    stranger = _caller(other_id, "member", authz)
    db_connection.execute("SET ROLE app_api")
    with pytest.raises(QueryAdmissionError, match="not_found"):
        delete_conversation(
            db_connection, caller=stranger, conversation_id=conversation_id
        )
    db_connection.execute("RESET ROLE")


def test_concurrent_read_during_delete_is_denied(
    db_url: str,
    db_connection: psycopg.Connection,
) -> None:
    """Readers wait on the delete lock and then see the tombstone."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        authz = _authorization_version(cursor)
    caller = _caller(user_id, "member", authz)
    db_connection.commit()

    blocker = psycopg.connect(db_url)
    blocker.autocommit = False
    blocker.execute("SET ROLE app_api")
    delete_conversation(blocker, caller=caller, conversation_id=conversation_id)

    seen: list[str] = []

    def _read() -> None:
        """Attempt a concurrent conversation read while delete holds a lock."""

        reader = psycopg.connect(db_url)
        reader.autocommit = False
        try:
            reader.execute("SET ROLE app_api")
            try:
                get_conversation(reader, caller=caller, conversation_id=conversation_id)
                seen.append("visible")
            except QueryAdmissionError as exc:
                seen.append(exc.reason)
            reader.rollback()
        finally:
            reader.close()

    worker = threading.Thread(target=_read)
    worker.start()
    worker.join(timeout=0.2)
    assert worker.is_alive()
    blocker.commit()
    worker.join(timeout=5)
    blocker.close()
    assert seen == ["not_found"]
    with psycopg.connect(db_url) as cleanup:
        cleanup.autocommit = True
        cleanup.execute(
            """
            DELETE FROM app.langsmith_deletion_requests
            WHERE conversation_id_hash = encode(
              sha256(convert_to(%s, 'UTF8')),
              'hex'
            )
            """,
            (str(conversation_id),),
        )
