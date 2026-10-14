"""Contract tests for SSE resume, sequence, cancel, and reconnect."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from smart_rag_api.services.sse_stream import FixtureQueryRunExecutor
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.sse.framing import iter_known_sse_events
from smart_rag_core.sse.store import MemoryRunEventStore, PostgresRunEventStore

from tests.contract.sse_http_support import (
    MEMBER_ID,
    OWNER_ID,
    RecordingAdmitService,
    client_headers,
    lifespanless_sse_app,
    patch_sse_rate_limits,
    require_str,
    sse_headers,
    sse_openapi_client,
)
from tests.support.query_postgres import (
    admit,
    authorization_version,
    caller_context,
    ensure_local_postgres,
    insert_conversation,
    insert_user_profile,
    retire_committed_query_run,
)
from tests.unit.typed_openapi import json_object


@pytest.fixture(autouse=True)
def permit_test_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow ``X-Test-*`` headers for SSE HTTP contract tests.

    Bypass requires ``APP_ENV=test`` and ``ALLOW_TEST_IDENTITY=true``.
    """

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")


def _sequences(raw: str) -> list[int]:
    """Return parsed SSE ids in order.

    Args:
        raw: EventSource body.

    Returns:
        Sequence numbers.
    """

    return [
        item.sequence
        for item in iter_known_sse_events(raw)
        if item.sequence is not None
    ]


def test_post_sse_sequences_are_monotonic_and_schema_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new stream persists schema then status then completed with increasing ids."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    key = str(uuid4())
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        response = client.post(
            f"/conversations/{uuid4()}/messages",
            json={"message": "hello", "idempotency_key": key},
            headers=sse_headers(),
        )
    assert response.status_code == 200
    events = iter_known_sse_events(response.text)
    assert events[0].event_type == "schema"
    seq = _sequences(response.text)
    assert seq == list(range(1, len(seq) + 1))
    assert "completed" in {item.event_type for item in events}
    assert executor.start_count == 1


def test_duplicate_idempotency_reuses_one_run_and_does_not_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate keys return the existing run and never start LangGraph twice."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    conversation_id = uuid4()
    key = str(uuid4())
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        first = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "hello", "idempotency_key": key},
            headers=sse_headers(),
        )
        second = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "hello", "idempotency_key": key},
            headers=sse_headers(),
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert admit.calls == 2
    assert executor.start_count == 1
    first_types = [item.event_type for item in iter_known_sse_events(first.text)]
    second_types = [item.event_type for item in iter_known_sse_events(second.text)]
    assert first_types[0] == "schema"
    assert "completed" in first_types
    assert "completed" in second_types


def test_resume_after_boundary_and_last_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume replays only sequence greater than ``after`` / Last-Event-ID."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    conversation_id = uuid4()
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        submitted = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "hello", "idempotency_key": str(uuid4())},
            headers=client_headers(),
        )
        payload = json_object(submitted.json())
        run_id = require_str(payload["run_id"])
        full = client.get(f"/runs/{run_id}/events", headers=sse_headers())
        after_one = client.get(
            f"/runs/{run_id}/events?after=1",
            headers=sse_headers(),
        )
        last_event = client.get(
            f"/runs/{run_id}/events",
            headers={**sse_headers(), "Last-Event-ID": "2"},
        )
    assert submitted.status_code == 202
    assert full.status_code == 200
    assert _sequences(full.text)[0] == 1
    assert iter_known_sse_events(full.text)[0].event_type == "schema"
    after_types = [item.event_type for item in iter_known_sse_events(after_one.text)]
    assert "schema" not in after_types
    assert _sequences(after_one.text)[0] == 2
    last_seq = _sequences(last_event.text)
    assert last_seq and last_seq[0] > 2
    assert executor.start_count == 1


def test_resume_reloads_requested_search_scope_without_second_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET run and resume reuse the stored scope and do not admit again."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    conversation_id = uuid4()
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        submitted = client.post(
            f"/conversations/{conversation_id}/messages",
            json={
                "message": "Parallel Tool Execution",
                "idempotency_key": str(uuid4()),
                "search_scope": "company_documents",
            },
            headers=client_headers(),
        )
        payload = json_object(submitted.json())
        run_id = require_str(payload["run_id"])
        fetched = client.get(f"/runs/{run_id}", headers=client_headers())
        resumed = client.get(f"/runs/{run_id}/events?after=0", headers=sse_headers())
    assert submitted.status_code == 202
    assert payload["requested_search_scope"] == "company_documents"
    assert fetched.status_code == 200
    assert json_object(fetched.json())["requested_search_scope"] == (
        "company_documents"
    )
    assert resumed.status_code == 200
    assert admit.calls == 1
    assert executor.start_count == 1


def test_foreign_missing_and_tombstoned_resume_are_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Foreign, missing, and tombstoned conversations deny resume with 404."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    conversation_id = uuid4()
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        submitted = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "hello", "idempotency_key": str(uuid4())},
            headers=client_headers(),
        )
        run_id = require_str(json_object(submitted.json())["run_id"])
        foreign = client.get(
            f"/runs/{run_id}/events",
            headers=sse_headers(MEMBER_ID, role="member"),
        )
        missing = client.get(
            f"/runs/{uuid4()}/events",
            headers=sse_headers(),
        )
        store.mark_conversation_deleted(conversation_id=UUID(str(conversation_id)))
        tombstoned = client.get(
            f"/runs/{run_id}/events",
            headers=sse_headers(),
        )
    assert foreign.status_code == 404
    assert json_object(foreign.json())["detail"] == "not_found"
    assert missing.status_code == 404
    assert tombstoned.status_code == 404
    assert executor.start_count == 1


def test_resume_does_not_require_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET resume of an already-admitted run does not require X-Client-Version."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        submitted = client.post(
            f"/conversations/{uuid4()}/messages",
            json={"message": "hello", "idempotency_key": str(uuid4())},
            headers=client_headers(),
        )
        run_id = require_str(json_object(submitted.json())["run_id"])
        headers = sse_headers()
        headers.pop("X-Client-Version")
        resumed = client.get(f"/runs/{run_id}/events", headers=headers)
    assert submitted.status_code == 202
    assert resumed.status_code == 200
    assert iter_known_sse_events(resumed.text)[0].event_type == "schema"


def test_process_restart_does_not_start_graph_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume on a replica while status is ``running`` replays only.

    It must not persist terminal ``error`` ``worker_unavailable``, which would
    block the owning replica from appending ``completed``.
    """

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    run_id = uuid4()
    caller = CallerContext(
        user_id=OWNER_ID,
        role=UserRole.OWNER,
        authorization_version=1,
    )
    store.register_run(
        caller=caller,
        record=QueryRunRecord(
            run_id=run_id,
            conversation_id=uuid4(),
            creator_user_id=UUID(OWNER_ID),
            status="running",
            reservation_id=uuid4(),
            created_at=None,
        ),
    )
    store.append(
        caller,
        run_id=run_id,
        event_type="schema",
        payload={"sse_schema_version": "1"},
    )
    store.append(
        caller,
        run_id=run_id,
        event_type="status",
        payload={"stage": "admitted", "status": "running"},
    )
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        restarted = client.get(f"/runs/{run_id}/events", headers=sse_headers())
    assert restarted.status_code == 200
    types = [item.event_type for item in iter_known_sse_events(restarted.text)]
    assert types == ["schema", "status"]
    assert "error" not in types
    assert executor.start_count == 0


def test_pending_orphan_without_input_emits_worker_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pending run with no live executor or POST body is a true orphan."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    run_id = uuid4()
    caller = CallerContext(
        user_id=OWNER_ID,
        role=UserRole.OWNER,
        authorization_version=1,
    )
    store.register_run(
        caller=caller,
        record=QueryRunRecord(
            run_id=run_id,
            conversation_id=uuid4(),
            creator_user_id=UUID(OWNER_ID),
            status="pending",
            reservation_id=uuid4(),
            created_at=None,
        ),
    )
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        restarted = client.get(f"/runs/{run_id}/events", headers=sse_headers())
    assert restarted.status_code == 200
    types = [item.event_type for item in iter_known_sse_events(restarted.text)]
    assert types[-1] == "error"
    error = next(
        item
        for item in iter_known_sse_events(restarted.text)
        if item.event_type == "error"
    )
    assert error.payload.get("code") == "worker_unavailable"
    assert executor.start_count == 0


def test_deadline_then_partial_is_durable_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deadline exhaustion emits ``deadline`` then ``partial`` and stops."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor(
        emit_completed=False,
        extra_events=(
            ("deadline", {"route_family": Phase6RouteFamily.COMPOSITE.value}),
            ("partial", {"reason": "deadline_exhausted"}),
        ),
    )
    admit = RecordingAdmitService()
    with sse_openapi_client(store=store, executor=executor, admit=admit) as client:
        response = client.post(
            f"/conversations/{uuid4()}/messages",
            json={"message": "hello", "idempotency_key": str(uuid4())},
            headers=sse_headers(),
        )
    types = [item.event_type for item in iter_known_sse_events(response.text)]
    assert "deadline" in types
    assert types[-1] == "partial"
    assert "completed" not in types
    assert "error" not in types


def test_cancel_stops_live_stream_and_persists_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST cancel stops the generator and persists a cancelled terminal."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor(hold_seconds=8, emit_completed=False)
    admit = RecordingAdmitService()
    application = lifespanless_sse_app(store=store, executor=executor, admit=admit)

    async def _run() -> None:
        """Cancel a held GET stream."""

        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            submitted = await client.post(
                f"/conversations/{uuid4()}/messages",
                json={"message": "hello", "idempotency_key": str(uuid4())},
                headers=client_headers(),
            )
            assert submitted.status_code == 202
            run_id = require_str(json_object(submitted.json())["run_id"])

            async def _read() -> str:
                """Drain the EventSource until cancelled or timeout."""

                chunks: list[str] = []
                async with client.stream(
                    "GET",
                    f"/runs/{run_id}/events",
                    headers=sse_headers(),
                ) as response:
                    assert response.status_code == 200
                    async for piece in response.aiter_text():
                        chunks.append(piece)
                        joined = "".join(chunks)
                        if any(
                            item.event_type == "cancelled"
                            for item in iter_known_sse_events(joined)
                        ):
                            break
                return "".join(chunks)

            reader = asyncio.create_task(_read())
            await asyncio.sleep(0.3)
            cancelled = await client.post(
                f"/runs/{run_id}/cancel",
                headers=client_headers(),
            )
            body = await asyncio.wait_for(reader, timeout=5)
            assert cancelled.status_code == 200
            assert json_object(cancelled.json())["status"] == "cancelled"
            types = [item.event_type for item in iter_known_sse_events(body)]
            assert "cancelled" in types
            assert "completed" not in types

    asyncio.run(_run())
    assert executor.start_count == 1


@pytest.fixture
def db_url() -> str:
    """Reuse the local Supabase helper from query-run admission tests.

    Returns:
        Postgres URL when local Supabase is reachable.
    """

    return ensure_local_postgres()


def test_postgres_append_is_monotonic_and_tombstone_denies(db_url: str) -> None:
    """Postgres sequences increase and tombstoned conversations 404."""

    owner = uuid4()
    stranger = uuid4()
    with psycopg.connect(db_url) as connection:
        connection.autocommit = False
        cursor = connection.cursor()
        insert_user_profile(cursor, user_id=owner, role="owner")
        insert_user_profile(cursor, user_id=stranger, role="member")
        conversation_id = insert_conversation(cursor, user_id=owner)
        version = authorization_version(cursor)
        caller = caller_context(owner, "owner", version)
        foreign = caller_context(stranger, "member", version)
        result, _key = admit(
            connection,
            caller=caller,
            conversation_id=conversation_id,
            route_family=Phase6RouteFamily.COMPOSITE,
        )
        connection.commit()
        run_id = result.context.run_id
        store = PostgresRunEventStore(db_url)
        first = store.append(
            caller,
            run_id=run_id,
            event_type="schema",
            payload={"sse_schema_version": "1"},
        )
        second = store.append(
            caller,
            run_id=run_id,
            event_type="status",
            payload={"stage": "admitted", "status": "running"},
        )
        third = store.append(caller, run_id=run_id, event_type="heartbeat", payload={})
        assert (first.sequence, second.sequence, third.sequence) == (1, 2, 3)
        after_one = store.list_after(caller, run_id=run_id, after=1)
        assert [item.sequence for item in after_one] == [2, 3]
        with pytest.raises(QueryAdmissionError) as foreign_exc:
            store.list_after(foreign, run_id=run_id, after=0)
        assert foreign_exc.value.reason == "not_found"
        connection.execute(
            """
            UPDATE app.conversations
            SET deleted_at = timezone('utc', now())
            WHERE id = %s
            """,
            (conversation_id,),
        )
        connection.commit()
        with pytest.raises(QueryAdmissionError) as tombstone_exc:
            store.list_after(caller, run_id=run_id, after=0)
        assert tombstone_exc.value.reason == "not_found"
        with connection.cursor() as denied:
            denied.execute("SET ROLE app_api")
            with pytest.raises(psycopg.Error):
                denied.execute(
                    """
                    INSERT INTO app.run_events (run_id, sequence, event_type, payload)
                    VALUES (%s, 99, 'status', '{}'::jsonb)
                    """,
                    (run_id,),
                )
        connection.rollback()
        retire_committed_query_run(
            db_url,
            run_id=run_id,
            reservation_id=result.context.reservation_id,
        )
