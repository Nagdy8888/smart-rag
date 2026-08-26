"""Contract tests for query memory reaper, deletion, store, summary, and LangSmith retry."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.conversations import delete_conversation, get_conversation
from smart_rag_core.feedback.tags import FEEDBACK_TAGS
from smart_rag_core.memory.reaper import (
    reap_query_run_retention,
    search_conversation_lingering_ids,
)
from smart_rag_core.memory.summary import (
    SUMMARY_DEFERRED,
    SUMMARY_WRITTEN,
    maybe_generate_conversation_summary,
)
from smart_rag_core.observability.langsmith_deletion import (
    RecordingLangSmithDeletionTransport,
    process_langsmith_deletion_requests,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import true_up_query_reservation

from tests.contract.integration_support import resolve_supabase_db_url, try_connect
from tests.contract.test_query_run_admission import (
    admit as _admit,
)
from tests.contract.test_query_run_admission import (
    authorization_version as _authorization_version,
)
from tests.contract.test_query_run_admission import (
    caller_context as _caller,
)
from tests.contract.test_query_run_admission import (
    insert_conversation as _insert_conversation,
)
from tests.contract.test_query_run_admission import (
    insert_user_profile as _insert_user_profile,
)

_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _ensure_local_postgres() -> str:
    """Return a reachable local Supabase URL or skip.

    Returns:
        Postgres URL on port 54322.

    Raises:
        pytest.skip: When the stack is unreachable.
    """

    url = resolve_supabase_db_url()
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


def _complete_run(
    cursor: psycopg.Cursor,
    run_id: UUID,
    *,
    completed_at: datetime,
) -> None:
    """Mark one run completed at an injected clock.

    Args:
        cursor: Open cursor.
        run_id: Run to complete.
        completed_at: Completion timestamp used by the reaper.
    """

    cursor.execute(
        """
        UPDATE app.runs
        SET
          status = 'completed'::app.run_status,
          completed_at = %s,
          updated_at = %s
        WHERE id = %s
        """,
        (completed_at, completed_at, run_id),
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
            (str(conversation_id), _NOW + timedelta(hours=24), _NOW),
        )
    transport = RecordingLangSmithDeletionTransport(fail_times=1)
    recorded, retried, expired = process_langsmith_deletion_requests(
        db_connection, transport=transport, now=_NOW
    )
    assert recorded == 0
    assert retried >= 1
    assert expired == 0
    recorded, retried, expired = process_langsmith_deletion_requests(
        db_connection, transport=transport, now=_NOW + timedelta(minutes=2)
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
            (_NOW - timedelta(hours=1), _NOW + timedelta(hours=25)),
        )
    late = RecordingLangSmithDeletionTransport()
    recorded, retried, expired = process_langsmith_deletion_requests(
        db_connection, transport=late, now=_NOW + timedelta(hours=25)
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
