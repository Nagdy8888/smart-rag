"""Production executor verified-final SSE and one-shot reservation settlement."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from smart_rag_agents.query.graph import compile_query_graph as _compile_query_graph
from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_api.services.sse_stream import (
    FixtureQueryRunExecutor,
    LangGraphQueryRunExecutor,
    QueryRunRegistry,
    SseStreamService,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.sse.store import MemoryRunEventStore, PostgresRunEventStore


def _caller() -> CallerContext:
    """Return a member caller with a stable UUID.

    Returns:
        Caller snapshot.
    """

    return CallerContext(
        user_id="00000000-0000-4000-8000-000000000011",
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _runtime(*, run_id: UUID | None = None) -> AuthorizedRuntimeContext:
    """Build a future-deadline authorized runtime.

    Args:
        run_id: Optional run id.

    Returns:
        Frozen runtime.
    """

    now = datetime.now(tz=UTC)
    return AuthorizedRuntimeContext(
        user_id=UUID("00000000-0000-4000-8000-000000000011"),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=run_id or uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now + timedelta(seconds=60),
        recursion_limit=8,
        correction_ceiling=1,
        subquestion_ceiling=0,
        model_call_ceiling=8,
        tool_ceiling=3,
        discovery_ceiling=0,
        manifest_ceiling=2,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("0.50"),
        remaining_usd=Decimal("0.50"),
        remaining_prompt_tokens=8000,
        remaining_completion_tokens=2000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="c" * 64,
        status="pending",
    )


class _FakeCompiled:
    """Compiled-graph stand-in that yields node-keyed updates."""

    def __init__(self, chunks: tuple[dict[str, object], ...]) -> None:
        """Store envelopes.

        Args:
            chunks: Node-keyed update mappings.
        """

        self._chunks = chunks

    async def astream(self, *args: object, **kwargs: object) -> Any:
        """Yield stored updates.

        Args:
            *args: Ignored graph input.
            **kwargs: Ignored stream options.

        Yields:
            Node-keyed envelopes.
        """

        del args, kwargs
        for chunk in self._chunks:
            yield chunk


def test_production_executor_emits_verified_delta_then_one_terminal(
    monkeypatch: Any,
) -> None:
    """LangGraph executor maps updates into schema-safe verified SSE."""

    commit_calls: list[str] = []
    draft = AnswerPayload(answer_text="DRAFT_HIDDEN", status="complete")
    final = AnswerPayload(answer_text="VISIBLE_FINAL", status="complete")
    compiled = _FakeCompiled(
        (
            {
                "generate_answer": {
                    "status": "drafted",
                    "answer": draft.model_dump(mode="json"),
                }
            },
            {
                "verify_answer": {
                    "status": "verified",
                    "answer": final.model_dump(mode="json"),
                }
            },
        )
    )
    monkeypatch.setattr(
        "smart_rag_core.settings.load_backend_settings",
        lambda: SimpleNamespace(
            langsmith_tracing=False,
            mock_model_mode=True,
            subprocessor_matrix_verified=True,
            allows_unsigned_local_live_providers=lambda: True,
            supabase_db_url=None,
        ),
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.governance_gate.assert_langsmith_export_permitted",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.query_run_trace.query_run_trace_metadata",
        lambda **kwargs: {},
    )
    graph_mod = sys.modules[_compile_query_graph.__module__]
    monkeypatch.setattr(
        graph_mod, "compile_query_graph", lambda *args, **kwargs: compiled
    )
    monkeypatch.setattr(
        graph_mod,
        "pending_query_state",
        lambda **kwargs: {"status": "pending"},
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.open_run_app_api_connection",
        lambda dsn: SimpleNamespace(
            commit=lambda: commit_calls.append("commit"),
            close=lambda: None,
        ),
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.build_query_graph_deps",
        lambda **kwargs: object(),
    )
    executor = LangGraphQueryRunExecutor()
    monkeypatch.setattr(
        executor,
        "_process_bindings",
        lambda settings: SimpleNamespace(supabase_dsn="postgresql://x"),
    )
    monkeypatch.setattr(executor, "_bind_memory_store", lambda settings: (None, None))
    monkeypatch.setattr(executor, "_maybe_summarize", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        executor, "_persist_assistant_answer", lambda *args, **kwargs: None
    )

    async def _collect() -> list[tuple[str, dict[str, object]]]:
        """Drain production executor events.

        Returns:
            SSE event name and payload pairs.
        """

        events: list[tuple[str, dict[str, object]]] = []
        cancel = asyncio.Event()
        async for event in executor.execute(
            context=_runtime(),
            message="hello",
            cancel_event=cancel,
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [item[0] for item in events]
    assert "schema" not in types
    assert types.count("completed") == 1
    assert types[-1] == "completed"
    deltas = [
        payload.get("delta")
        for event_type, payload in events
        if event_type == "token_delta"
    ]
    assert deltas == ["VISIBLE_FINAL"]
    assert "DRAFT_HIDDEN" not in str(events)
    assert any(event_type == "status" for event_type in types)
    assert commit_calls == ["commit", "commit"]


def test_production_executor_empty_answer_cannot_complete(monkeypatch: Any) -> None:
    """Verified empty prose becomes error, never completed."""

    compiled = _FakeCompiled(
        (
            {
                "generate_answer": {
                    "status": "drafted",
                    "answer": AnswerPayload(
                        answer_text="x", status="complete"
                    ).model_dump(mode="json"),
                }
            },
            {
                "verify_answer": {
                    "status": "verified",
                    "answer": AnswerPayload(
                        answer_text="  ", status="complete"
                    ).model_dump(mode="json"),
                }
            },
        )
    )
    monkeypatch.setattr(
        "smart_rag_core.settings.load_backend_settings",
        lambda: SimpleNamespace(
            langsmith_tracing=False,
            mock_model_mode=True,
            subprocessor_matrix_verified=True,
            allows_unsigned_local_live_providers=lambda: True,
            supabase_db_url=None,
        ),
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.governance_gate.assert_langsmith_export_permitted",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.query_run_trace.query_run_trace_metadata",
        lambda **kwargs: {},
    )
    graph_mod = sys.modules[_compile_query_graph.__module__]
    monkeypatch.setattr(
        graph_mod, "compile_query_graph", lambda *args, **kwargs: compiled
    )
    monkeypatch.setattr(
        graph_mod,
        "pending_query_state",
        lambda **kwargs: {"status": "pending"},
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.open_run_app_api_connection",
        lambda dsn: SimpleNamespace(commit=lambda: None, close=lambda: None),
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.build_query_graph_deps",
        lambda **kwargs: object(),
    )
    executor = LangGraphQueryRunExecutor()
    monkeypatch.setattr(
        executor,
        "_process_bindings",
        lambda settings: SimpleNamespace(supabase_dsn="postgresql://x"),
    )
    monkeypatch.setattr(executor, "_bind_memory_store", lambda settings: (None, None))
    monkeypatch.setattr(executor, "_maybe_summarize", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        executor, "_persist_assistant_answer", lambda *args, **kwargs: None
    )

    async def _collect() -> list[tuple[str, dict[str, object]]]:
        """Drain empty-answer executor events.

        Returns:
            SSE event name and payload pairs.
        """

        events: list[tuple[str, dict[str, object]]] = []
        async for event in executor.execute(
            context=_runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [item[0] for item in events]
    assert "completed" not in types
    assert types[-1] == "error"
    assert events[-1][1].get("code") == "empty_answer"


def test_production_executor_keeps_partial_when_summary_fails(
    monkeypatch: Any,
) -> None:
    """Post-terminal summary failure must not replace partial with error."""

    final = AnswerPayload(answer_text="Hello there.", status="partial")
    compiled = _FakeCompiled(
        (
            {
                "generate_answer": {
                    "status": "answered",
                    "answer": final.model_dump(mode="json"),
                }
            },
            {
                "verify_answer": {
                    "status": "verified_partial",
                    "answer": final.model_dump(mode="json"),
                }
            },
        )
    )
    monkeypatch.setattr(
        "smart_rag_core.settings.load_backend_settings",
        lambda: SimpleNamespace(
            langsmith_tracing=False,
            mock_model_mode=True,
            subprocessor_matrix_verified=True,
            allows_unsigned_local_live_providers=lambda: True,
            supabase_db_url=None,
        ),
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.governance_gate.assert_langsmith_export_permitted",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "smart_rag_core.observability.query_run_trace.query_run_trace_metadata",
        lambda **kwargs: {},
    )
    graph_mod = sys.modules[_compile_query_graph.__module__]
    monkeypatch.setattr(
        graph_mod, "compile_query_graph", lambda *args, **kwargs: compiled
    )
    monkeypatch.setattr(
        graph_mod,
        "pending_query_state",
        lambda **kwargs: {"status": "pending"},
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.open_run_app_api_connection",
        lambda dsn: SimpleNamespace(commit=lambda: None, close=lambda: None),
    )
    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.build_query_graph_deps",
        lambda **kwargs: object(),
    )
    executor = LangGraphQueryRunExecutor()
    monkeypatch.setattr(
        executor,
        "_process_bindings",
        lambda settings: SimpleNamespace(supabase_dsn="postgresql://x"),
    )
    monkeypatch.setattr(executor, "_bind_memory_store", lambda settings: (None, None))

    def _boom(*args: object, **kwargs: object) -> None:
        """Raise the hosted summary failure observed on greeting runs.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Raises:
            QueryAdmissionError: Always.
        """

        del args, kwargs
        raise QueryAdmissionError("message_persist_failed")

    monkeypatch.setattr(executor, "_maybe_summarize", _boom)
    monkeypatch.setattr(
        executor, "_persist_assistant_answer", lambda *args, **kwargs: None
    )

    async def _collect() -> list[tuple[str, dict[str, object]]]:
        """Drain summary-failure executor events.

        Returns:
            SSE event name and payload pairs.
        """

        events: list[tuple[str, dict[str, object]]] = []
        async for event in executor.execute(
            context=_runtime(),
            message="hi",
            cancel_event=asyncio.Event(),
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [item[0] for item in events]
    assert types.count("partial") == 1
    assert types[-1] == "partial"
    assert "error" not in types
    assert any(
        event_type == "token_delta" and payload.get("delta") == "Hello there."
        for event_type, payload in events
    )


def test_sse_service_settles_reservation_once_on_terminal(monkeypatch: Any) -> None:
    """Terminal persist true-ups the reservation exactly once."""

    calls: list[UUID] = []

    class _Conn:
        """No-op connection used by settlement."""

        def execute(self, statement: str) -> None:
            """Ignore SET ROLE.

            Args:
                statement: SQL.
            """

            del statement

        def commit(self) -> None:
            """No-op commit."""

            return None

        def __enter__(self) -> _Conn:
            """Enter the dummy connection context.

            Returns:
                This connection.
            """

            return self

        def __exit__(self, *args: object) -> None:
            """Ignore context-exit arguments.

            Args:
                *args: Exception context unused by the stub.
            """

            del args

    def _connect(url: str) -> _Conn:
        """Return the no-op connection.

        Args:
            url: DSN.

        Returns:
            Dummy connection.
        """

        del url
        return _Conn()

    def _true_up(
        connection: object, *, caller: CallerContext, reservation_id: UUID
    ) -> None:
        """Record settlement.

        Args:
            connection: Unused.
            caller: Owner.
            reservation_id: Reservation.
        """

        del connection, caller
        calls.append(reservation_id)

    monkeypatch.setattr("smart_rag_api.services.sse_stream.psycopg.connect", _connect)
    monkeypatch.setattr(
        "smart_rag_api.services.sse_stream.true_up_query_reservation",
        _true_up,
    )
    store = MemoryRunEventStore()
    registry = QueryRunRegistry()
    executor = FixtureQueryRunExecutor()
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=executor,
        sse_schema_version="1",
        postgres_url="postgresql://example",
    )
    caller = _caller()
    runtime = _runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> list[str]:
        """Collect SSE frames from the stream service.

        Returns:
            Raw SSE frame strings.
        """

        frames: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            frames.append(frame)
        return frames

    frames = asyncio.run(_drain())
    assert any(
        "event: completed" in frame or "event: error" in frame for frame in frames
    )
    assert calls == [runtime.reservation_id]
    service._append(caller, runtime.run_id, "error", {"code": "run_failed"})
    assert calls == [runtime.reservation_id]


def test_sse_service_fallthrough_without_terminal_is_error_not_completed() -> None:
    """If the executor yields no terminal, persist error rather than completed."""

    store = MemoryRunEventStore()
    registry = QueryRunRegistry()
    executor = FixtureQueryRunExecutor(emit_completed=False)
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=executor,
        sse_schema_version="1",
    )
    caller = _caller()
    runtime = _runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> list[str]:
        """Collect SSE frames from the stream service.

        Returns:
            Raw SSE frame strings.
        """

        frames: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            frames.append(frame)
        return frames

    frames = asyncio.run(_drain())
    joined = "".join(frames)
    assert "event: completed" not in joined
    assert "event: error" in joined
    assert "run_failed" in joined


def test_mapper_type_is_exported_for_executor() -> None:
    """Executor persist path depends on QuerySseMapper.verified_text."""

    mapper = QuerySseMapper()
    assert mapper.verified_text == ""


def test_postgres_event_store_reuses_and_closes_session(monkeypatch: Any) -> None:
    """Hosted SSE transactions reuse one connection and close it explicitly."""

    calls: list[str] = []
    connection = SimpleNamespace(closed=False)

    def _execute(statement: str) -> None:
        """Record one connection statement.

        Args:
            statement: SQL statement.
        """

        calls.append(statement)

    def _commit() -> None:
        """Record a successful transaction commit."""

        calls.append("COMMIT")

    def _rollback() -> None:
        """Record a transaction rollback."""

        calls.append("ROLLBACK")

    def _close() -> None:
        """Mark the fake connection closed."""

        connection.closed = True
        calls.append("CLOSE")

    def _connect(url: str, *, prepare_threshold: int | None) -> object:
        """Return the single fake connection.

        Args:
            url: Connection URL.
            prepare_threshold: Automatic statement preparation threshold.

        Returns:
            Fake reusable connection.
        """

        calls.append(f"CONNECT {url} PREPARE {prepare_threshold}")
        return connection

    connection.execute = _execute
    connection.commit = _commit
    connection.rollback = _rollback
    connection.close = _close
    monkeypatch.setattr("smart_rag_core.sse.store.psycopg.connect", _connect)
    store = PostgresRunEventStore("postgresql://hosted")

    with store._transaction():
        pass
    with store._transaction():
        pass
    store.close()

    assert calls.count("CONNECT postgresql://hosted PREPARE None") == 1
    assert calls.count("SET ROLE app_api") == 2
    assert calls.count("COMMIT") == 2
    assert calls[-1] == "CLOSE"
