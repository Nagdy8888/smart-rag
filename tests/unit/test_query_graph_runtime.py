"""Live SSE query-graph adapter wiring. Unbound deps are not the default."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from smart_rag_agents.prompts import answer_prompt_text, verifier_prompt_text
from smart_rag_agents.query.checkpointer import (
    QUERY_CHECKPOINTER_POOL_MAX_SIZE,
    open_query_async_checkpointer,
    open_query_checkpointer,
)
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    gateway_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.answer import generate_answer_node
from smart_rag_agents.query.nodes.verify import verify_answer_node
from smart_rag_agents.query.runtime.adapters import context_loader
from smart_rag_agents.query.state import pending_query_state
from smart_rag_api.services.query_graph_runtime import (
    QueryGraphRuntimeError,
    build_query_graph_deps,
    build_query_process_bindings,
)
from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_api.services.sse_stream import LangGraphQueryRunExecutor
from smart_rag_core.gateways.model import AnswerModelResponse, create_model_gateway
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import mock_answer_payload
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.runtime.valkey import MemoryValkeyClient
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import SharedSettings

from tests.support.query_runtime import RefusingHybridRetriever
from tests.unit.typed_attrs import set_attr, typed_attr

_FAKE_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


class _CountedAnswerGateway:
    """Gateway that reports non-zero answer tokens without opening a socket."""

    async def generate_answer(self, request: object) -> AnswerModelResponse:
        """Return a complete answer fixture with counted usage.

        Args:
            request: Unused structured answer request.

        Returns:
            Mock answer response with 12 prompt and 7 completion tokens.
        """

        del request
        return AnswerModelResponse(
            mode="mock",
            payload={
                "answer_text": "Counted answer from authorized evidence.",
                "citations": [],
                "atomic_links": [],
                "composed_conclusion": None,
                "table_citations": [],
                "status": "complete",
            },
            request_id="counted-answer",
            input_tokens=12,
            output_tokens=7,
        )


def _fusion() -> FusionResult:
    """Return Hybrid-effective fusion with one canonical passage.

    Returns:
        Frozen fusion result.
    """

    passage = ScoredPassage(
        chunk_id="00000001-0000-4000-8000-000000000000",
        document_id="00000002-0000-4000-8000-000000000000",
        version_id="00000003-0000-4000-8000-000000000000",
        citation_text="The refund period is 30 days.",
        hybrid_rank=1,
        combined_score=1.0,
        origin=PassageOrigin.HYBRID,
        graph_discovered_only=False,
    )
    return FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
        requested_route="hybrid",
        effective_route="hybrid",
        evidence=(passage,),
        graph_discovered_only_ratio=0.0,
    )


def test_query_checkpointer_pool_covers_signed_concurrency() -> None:
    """Checkpointer pool default is at least five concurrent query runs."""

    assert QUERY_CHECKPOINTER_POOL_MAX_SIZE >= 5
    default = signature(open_query_checkpointer).parameters["max_size"].default
    assert default == QUERY_CHECKPOINTER_POOL_MAX_SIZE
    async_default = (
        signature(open_query_async_checkpointer).parameters["max_size"].default
    )
    assert async_default == QUERY_CHECKPOINTER_POOL_MAX_SIZE
    assert typed_attr(AsyncPostgresSaver, "aget_tuple") is not typed_attr(
        BaseCheckpointSaver, "aget_tuple"
    )
    assert typed_attr(PostgresSaver, "aget_tuple") is typed_attr(
        BaseCheckpointSaver, "aget_tuple"
    )
    with pytest.raises(ValueError, match="LANGGRAPH_CHECKPOINT_URL"):
        asyncio.run(
            open_query_async_checkpointer(
                "postgresql://unit:secret@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
            )
        )


def test_default_process_bindings_have_hybrid_and_gateway() -> None:
    """Live SSE construction binds Hybrid and a gateway, including mock mode."""

    bindings = build_query_process_bindings(
        settings=SharedSettings(mock_model_mode=True),
        supabase_dsn=_FAKE_DSN,
        paradedb_url=None,
    )
    assert bindings.hybrid_retriever is not None
    assert bindings.model_gateway is not None
    assert bindings.graph_retriever is None
    assert bindings.answer_prompt_text
    assert bindings.verifier_prompt_text
    deps = build_query_graph_deps(
        bindings=bindings,
        connection=None,
        cancel_check=lambda: False,
    )
    assert deps.hybrid_retriever is not None
    assert deps.model_gateway is not None
    empty = QueryGraphDeps()
    assert empty.hybrid_retriever is None
    assert empty.model_gateway is None


def test_process_bindings_inject_retrieval_cache_from_app_state() -> None:
    """Valkey on app.state is injected as an ID-only retrieval cache."""

    client = MemoryValkeyClient()
    bindings = build_query_process_bindings(
        settings=SharedSettings(mock_model_mode=True),
        supabase_dsn=_FAKE_DSN,
        app_state=SimpleNamespace(valkey_cache_client=client),
    )
    hybrid = bindings.hybrid_retriever
    assert getattr(hybrid, "_retrieval_cache", None) is not None


def test_sse_execute_does_not_continue_without_app_api_connection() -> None:
    """Failed ``app_api`` connect must surface as SSE error, not ``connection=None``."""

    runtime_source = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "backend"
        / "src"
        / "smart_rag_api"
        / "services"
        / "sse"
        / "langgraph_runtime.py"
    ).read_text(encoding="utf-8")
    execute_source = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "backend"
        / "src"
        / "smart_rag_api"
        / "services"
        / "sse"
        / "langgraph_execute.py"
    ).read_text(encoding="utf-8")
    executor_source = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "backend"
        / "src"
        / "smart_rag_api"
        / "services"
        / "sse"
        / "langgraph_executor.py"
    ).read_text(encoding="utf-8")
    assert (
        "except QueryGraphRuntimeError:\n                connection = None"
        not in runtime_source
    )
    assert "except QueryGraphRuntimeError:\n                connection = None" not in (
        execute_source
    )
    assert "except QueryGraphRuntimeError:\n                connection = None" not in (
        executor_source
    )
    assert "open_run_app_api_connection_async(bindings.supabase_dsn)" in runtime_source
    assert 'yield ("error", {"code": exc.reason})' in execute_source


def test_context_loader_keeps_connection_idle_for_retrieval_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context fetch must not SET ROLE before retrieval_transaction.

    Hosted transaction-pooler and local Postgres both start a transaction on
    the first ``SET ROLE``. ``retrieval_transaction`` then raises
    ``retrieval_requires_idle_connection``.
    """

    executed: list[str] = []

    class _Conn:
        """Record execute() so the test can prove the loader stays idle."""

        def execute(self, sql: str) -> None:
            """Record SQL issued on the fresh connection.

            Args:
                sql: Statement text.
            """

            executed.append(sql)

        def close(self) -> None:
            """Close the stub connection."""

            return None

        def __enter__(self) -> _Conn:
            """Enter the connect context."""

            return self

        def __exit__(self, *_args: object) -> None:
            """Exit the connect context."""

            return None

    def _connect(_dsn: str, **_kwargs: object) -> _Conn:
        """Return the stub connection."""

        return _Conn()

    fetched: list[object] = []

    def _fetch(
        connection: object,
        *,
        caller: CallerContext,
        chunk_ids: tuple[object, ...],
    ) -> tuple[()]:
        """Capture the idle connection and return no rows.

        Args:
            connection: Connection passed by the loader.
            caller: Retrieve caller.
            chunk_ids: Requested IDs.

        Returns:
            Empty authorized context.
        """

        del caller, chunk_ids
        fetched.append(connection)
        return ()

    monkeypatch.setattr(
        "smart_rag_agents.query.runtime.adapters_hybrid.connect_postgres",
        _connect,
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.runtime.adapters_hybrid.fetch_authorized_chunk_context",
        _fetch,
    )
    loader = context_loader(
        _FAKE_DSN,
        CallerContext(
            user_id=str(uuid4()),
            role=UserRole.MEMBER,
            authorization_version=1,
        ),
    )
    assert loader((uuid4(),)) == ()
    assert executed == []
    assert len(fetched) == 1


def test_missing_supabase_dsn_fails_closed() -> None:
    """Hybrid cannot be constructed without a canonical DSN."""

    try:
        build_query_process_bindings(
            settings=SharedSettings(mock_model_mode=True), supabase_dsn=""
        )
    except QueryGraphRuntimeError as exc:
        assert exc.reason == "hybrid_retriever_unbound"
    else:
        raise AssertionError("expected hybrid_retriever_unbound")


def test_per_run_cancel_check_is_not_shared_across_deps() -> None:
    """Process Hybrid may be reused; cancel_check stays per compiled run."""

    bindings = build_query_process_bindings(
        settings=SharedSettings(mock_model_mode=True),
        supabase_dsn=_FAKE_DSN,
    )
    first = build_query_graph_deps(
        bindings=bindings,
        connection=None,
        cancel_check=lambda: False,
    )
    second = build_query_graph_deps(
        bindings=bindings,
        connection=None,
        cancel_check=lambda: True,
    )
    assert first.cancel_check is not second.cancel_check
    assert first.cancel_check is not None
    assert second.cancel_check is not None
    assert first.cancel_check() is False
    assert second.cancel_check() is True
    assert first.hybrid_retriever is not second.hybrid_retriever
    assert getattr(first.hybrid_retriever, "inner", None) is bindings.hybrid_retriever


def test_executor_default_bindings_are_not_empty_query_graph_deps() -> None:
    """LangGraphQueryRunExecutor reuses process bindings, not empty QueryGraphDeps."""

    executor = LangGraphQueryRunExecutor()
    bindings = build_query_process_bindings(
        settings=SharedSettings(mock_model_mode=True),
        supabase_dsn=_FAKE_DSN,
    )
    set_attr(executor, "_bindings", bindings)
    cached = typed_attr(executor, "_process_bindings")(
        SharedSettings(mock_model_mode=True)
    )
    assert cached.hybrid_retriever is not None
    assert cached.model_gateway is not None
    assert cached is bindings


def test_bound_mock_gateway_drives_sse_without_token_injection() -> None:
    """Production generate/verify uses a bound mock gateway, not injected deltas.

    Acceptance:
        ``create_model_gateway(mock_model_mode=True)`` is the answer adapter.
        Mapper events come from real node outputs. An SSE fixture that yields
        ``token_delta`` without running generate/verify is insufficient.
    """

    settings = SharedSettings(mock_model_mode=True)
    gateway = create_model_gateway(settings)
    deps = QueryGraphDeps(
        hybrid_retriever=RefusingHybridRetriever(),
        model_gateway=gateway,
        answer_prompt_text=answer_prompt_text(),
        verifier_prompt_text=verifier_prompt_text(),
    )
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 8
    state["fusion"] = _fusion().model_dump(mode="json")
    generated = generate_answer_node(state, deps)
    generated_answer = AnswerPayload.model_validate(generated["answer"])
    assert generated_answer.answer_text.strip()
    verified = verify_answer_node(generated, deps)
    mapper = QuerySseMapper()
    events = list(mapper.consume_chunk({"generate_answer": generated}))
    events.extend(mapper.consume_chunk({"verify_answer": verified}))
    if not mapper.terminal_emitted:
        events.extend(mapper.finish())
    types = [item[0] for item in events]
    terminals = [
        name for name in types if name in {"completed", "partial", "error", "cancelled"}
    ]
    assert len(terminals) == 1
    if verified["status"] == "verified" and generated_answer.answer_text.strip():
        assert types.count("completed") == 1
        deltas = [
            payload.get("delta")
            for event_type, payload in events
            if event_type == "token_delta"
        ]
        assert "".join(str(item or "") for item in deltas).strip()
    else:
        assert "completed" not in types or verified["status"] == "verified"


def test_generate_answer_accumulates_provider_tokens() -> None:
    """Answer generation copies gateway token counts onto query state."""

    deps = QueryGraphDeps(
        hybrid_retriever=RefusingHybridRetriever(),
        model_gateway=_CountedAnswerGateway(),
        answer_prompt_text=answer_prompt_text(),
    )
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 8
    state["fusion"] = _fusion().model_dump(mode="json")
    generated = generate_answer_node(state, deps)
    assert generated["prompt_tokens"] == 12
    assert generated["completion_tokens"] == 7
    mapper = QuerySseMapper()
    mapper.consume_chunk({"generate_answer": generated})
    mapper.consume_chunk({"verify_answer": generated})
    events = mapper.finish()
    usage = [payload for event_type, payload in events if event_type == "usage"]
    assert usage == [{"prompt_tokens": 12, "completion_tokens": 7}]


def test_unbound_hybrid_never_emits_verified() -> None:
    """Missing Hybrid on a retrieval route is insufficient_evidence, not verified."""

    fusion = _fusion()
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 5
    state["fusion"] = fusion.model_dump(mode="json")
    out = generate_answer_node(state, QueryGraphDeps())
    assert out["status"] == "insufficient_evidence"
    assert out["status"] != "verified"


def test_unbound_gateway_with_hybrid_is_verified_partial() -> None:
    """Evidence without a gateway cannot terminate verified."""

    fusion = _fusion()
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 5
    state["fusion"] = fusion.model_dump(mode="json")
    deps = QueryGraphDeps(hybrid_retriever=RefusingHybridRetriever())
    out = generate_answer_node(state, deps)
    assert out["status"] == "verified_partial"
    assert out["detail"] == "model_gateway_unbound"
    payload = AnswerPayload.model_validate(out["answer"])
    assert payload.status == "partial"


def test_run_coro_from_running_loop_does_not_raise() -> None:
    """Gateway helpers must not nest asyncio.run on the live SSE loop."""

    async def _inner() -> str:
        """Return a sentinel from a nested awaitable.

        Returns:
            Fixed token.
        """

        await asyncio.sleep(0)
        return "ok"

    async def _outer() -> object:
        """Invoke ``_run_coro`` while a loop is already running.

        Returns:
            Worker-thread gateway result.
        """

        return run_coro(lambda: _inner())

    assert asyncio.run(_outer()) == "ok"


def test_run_coro_does_not_wait_for_langsmith_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry draining is forbidden on the post-model answer path."""

    from smart_rag_core.observability import langsmith_tracing as tracing

    def _slow_flush(*, timeout_seconds: float) -> None:
        """Model the blocking exporter that caused the production latency.

        Args:
            timeout_seconds: Unused simulated drain bound.
        """

        del timeout_seconds
        time.sleep(0.5)

    async def _answer() -> str:
        """Return one completed model result.

        Returns:
            Fixed answer token.
        """

        return "ready"

    monkeypatch.setattr(tracing, "flush_langsmith_traces", _slow_flush)
    started = time.monotonic()
    result = run_coro(lambda: _answer(), timeout_seconds=1.0)
    elapsed = time.monotonic() - started
    assert result == "ready"
    assert elapsed < 0.3


def test_run_coro_honors_cancel_check() -> None:
    """Dedicated-thread gateway waits abort when cancel_check fires."""

    async def _slow() -> str:
        """Sleep longer than the cancel poll.

        Returns:
            Unreachable token.
        """

        await asyncio.sleep(30)
        return "late"

    async def _outer() -> None:
        """Start ``_run_coro`` on the running loop and cancel immediately."""

        run_coro(lambda: _slow(), cancel_check=lambda: True, timeout_seconds=5)

    try:
        asyncio.run(_outer())
    except AnswerError as exc:
        assert exc.reason == "cancelled"
    else:
        raise AssertionError("expected cancelled")


def test_gateway_timeout_uses_run_deadline_not_model_call_count() -> None:
    """Hosted live OpenAI must not treat remaining model calls as seconds."""

    assert gateway_timeout_seconds(None) == 20.0
    far = SimpleNamespace(deadline_at=datetime.now(UTC) + timedelta(seconds=30))
    timeout = gateway_timeout_seconds(far)  # type: ignore[arg-type]
    assert 20.0 <= timeout <= 30.0
    near = SimpleNamespace(deadline_at=datetime.now(UTC) + timedelta(seconds=2))
    assert 0.1 <= gateway_timeout_seconds(near) <= 2.0  # type: ignore[arg-type]


def test_run_coro_wraps_provider_errors_without_a_running_loop() -> None:
    """Sync graph threads must surface AnswerError, not raw provider types."""

    async def _boom() -> str:
        """Raise a provider-shaped failure.

        Returns:
            Unreachable token.
        """

        raise RuntimeError("answer_timeout")

    try:
        run_coro(lambda: _boom())
    except AnswerError as exc:
        assert exc.reason == "gateway_failed"
    else:
        raise AssertionError("expected gateway_failed")


def test_run_coro_times_out_without_a_running_loop() -> None:
    """Sync LangGraph workers must bound an unresponsive async gateway."""

    async def _slow() -> str:
        """Sleep beyond the configured gateway deadline.

        Returns:
            Unreachable token.
        """

        await asyncio.sleep(30)
        return "late"

    try:
        run_coro(lambda: _slow(), timeout_seconds=0.01)
    except TimeoutAfterSendError:
        pass
    else:
        raise AssertionError("expected timeout_after_send")


def test_mock_answer_is_not_used_as_verified_success() -> None:
    """Extractive mock payload is not a live verified answer."""

    fusion = _fusion()
    payload = mock_answer_payload(fusion, (), user_query="refund")
    assert payload.status in {"complete", "partial"}
    deps = QueryGraphDeps(hybrid_retriever=RefusingHybridRetriever())
    state = pending_query_state(user_query="refund")
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 5
    state["fusion"] = fusion.model_dump(mode="json")
    out = generate_answer_node(state, deps)
    assert out["status"] != "verified"
