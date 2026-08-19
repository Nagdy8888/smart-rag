"""Live SSE query-graph adapter wiring. Unbound deps are not the default."""

from __future__ import annotations

import asyncio
from inspect import signature
from pathlib import Path

import smart_rag_core.retrieval.hybrid_run as _hybrid_run_cycle_guard  # noqa: F401
from smart_rag_agents.query.checkpointer import (
    QUERY_CHECKPOINTER_POOL_MAX_SIZE,
    open_query_checkpointer,
)
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.pipeline import _run_coro, generate_answer_node
from smart_rag_agents.query.state import pending_query_state
from smart_rag_api.services.query_graph_runtime import (
    QueryGraphRuntimeError,
    build_query_graph_deps,
    build_query_process_bindings,
)
from smart_rag_api.services.sse_stream import LangGraphQueryRunExecutor
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
from smart_rag_core.settings import SharedSettings

_FAKE_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


class _DummyHybrid:
    """Truthy Hybrid adapter used to prove generate fail-closed without retrieve."""

    def retrieve(self, **kwargs: object) -> object:
        """Refuse accidental retrieve.

        Args:
            **kwargs: Ignored retrieve keywords.

        Raises:
            AssertionError: Always. Generate must not retrieve.
        """

        del kwargs
        raise AssertionError("hybrid retrieve must not run in this test")


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


def test_sse_execute_does_not_continue_without_app_api_connection() -> None:
    """Failed ``app_api`` connect must surface as SSE error, not ``connection=None``."""

    source = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "backend"
        / "src"
        / "smart_rag_api"
        / "services"
        / "sse_stream.py"
    ).read_text(encoding="utf-8")
    assert (
        "except QueryGraphRuntimeError:\n                connection = None"
        not in source
    )
    assert "open_run_app_api_connection(bindings.supabase_dsn)" in source
    assert 'yield ("error", {"code": exc.reason})' in source


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
    executor._bindings = bindings
    cached = executor._process_bindings(SharedSettings(mock_model_mode=True))
    assert cached.hybrid_retriever is not None
    assert cached.model_gateway is not None
    assert cached is bindings


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
    deps = QueryGraphDeps(hybrid_retriever=_DummyHybrid())
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

        return _run_coro(lambda: _inner())

    assert asyncio.run(_outer()) == "ok"


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

        _run_coro(lambda: _slow(), cancel_check=lambda: True, timeout_seconds=5)

    try:
        asyncio.run(_outer())
    except AnswerError as exc:
        assert exc.reason == "cancelled"
    else:
        raise AssertionError("expected cancelled")


def test_mock_answer_is_not_used_as_verified_success() -> None:
    """Extractive mock payload is not a live verified answer."""

    fusion = _fusion()
    payload = mock_answer_payload(fusion, (), user_query="refund")
    assert payload.status in {"complete", "partial"}
    deps = QueryGraphDeps(hybrid_retriever=_DummyHybrid())
    state = pending_query_state(user_query="refund")
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 5
    state["fusion"] = fusion.model_dump(mode="json")
    out = generate_answer_node(state, deps)
    assert out["status"] != "verified"
