"""Route-aware production progress: required stages and skipped nodes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.state import pending_query_state
from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_api.services.sse.stream_dispatch import dispatch_stream_part
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole

from tests.unit.test_scope_graph_routes import _COMPANY_ONLY_NODES, _SpyHybrid

_GENERAL_REQUIRED = {
    "enforce_admission",
    "load_memory",
    "prepare_query",
    "compile_plan",
    "general_scope",
    "verify_answer",
}
_MIXED_REQUIRED = {
    "enforce_admission",
    "load_memory",
    "prepare_query",
    "compile_plan",
    "mixed_scope",
    "verify_answer",
}
_COMPANY_REQUIRED = {
    "enforce_admission",
    "load_memory",
    "prepare_query",
    "compile_plan",
    "company_scope",
    "apply_correction",
}
_INVALID_REQUIRED = {
    "enforce_admission",
    "load_memory",
    "prepare_query",
    "compile_plan",
    "invalid_scope",
}


def _runtime() -> AuthorizedRuntimeContext:
    """Return a Composite admission envelope for route-progress tests.

    Returns:
        Frozen authorized runtime context.
    """

    now = datetime.now(UTC)
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now + timedelta(seconds=50),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=9,
        tool_ceiling=5,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("3.60"),
        remaining_usd=Decimal("3.60"),
        remaining_prompt_tokens=72000,
        remaining_completion_tokens=18000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="b" * 64,
        status="pending",
    )


def _collect_route(
    query: str,
    *,
    hybrid: _SpyHybrid | None = None,
) -> tuple[list[tuple[str, dict[str, object]]], list[str], list[str]]:
    """Stream one admitted run and map v2 parts to catalog drafts.

    Args:
        query: Original user text.
        hybrid: Optional Hybrid spy.

    Returns:
        Catalog drafts, start stages, and completed/failed stages.
    """

    compiled = build_query_graph(QueryGraphDeps(hybrid_retriever=hybrid)).compile()
    state = pending_query_state(_runtime().model_dump(mode="json"), user_query=query)
    mapper = QuerySseMapper()
    drafts: list[tuple[str, dict[str, object]]] = []
    for raw in compiled.stream(
        state,
        stream_mode=["updates", "custom"],
        version="v2",
    ):
        dispatched = dispatch_stream_part(raw, mapper)
        drafts.extend(dispatched.drafts)
    drafts.extend(mapper.finish())
    starts = [
        str(item[1].get("stage"))
        for item in drafts
        if item[0] == "status" and item[1].get("phase") == "started"
    ]
    terminals = [
        str(item[1].get("stage"))
        for item in drafts
        if item[0] == "status" and item[1].get("phase") in {"completed", "failed"}
    ]
    return drafts, starts, terminals


def _assert_one_start_at_most_one_terminal(
    starts: list[str], terminals: list[str]
) -> None:
    """Every start has at most one later terminal status.

    Args:
        starts: Started stages in order.
        terminals: Completed or failed stages in order.
    """

    assert len(starts) == len(set(starts))
    counts: dict[str, int] = {}
    for stage in terminals:
        counts[stage] = counts.get(stage, 0) + 1
    assert all(count <= 1 for count in counts.values())
    for stage in starts:
        assert counts.get(stage, 0) <= 1


def test_general_route_skips_company_nodes_and_tools() -> None:
    """Greeting path emits general+verify and no company or tool events."""

    query = "Hello"
    drafts, starts, terminals = _collect_route(query)
    _assert_one_start_at_most_one_terminal(starts, terminals)
    assert _GENERAL_REQUIRED <= set(starts)
    assert _COMPANY_ONLY_NODES.isdisjoint(starts)
    assert "mixed_scope" not in starts
    assert "invalid_scope" not in starts
    assert not any(item[0] == "tool_progress" for item in drafts)
    serialized = str(drafts)
    assert query not in serialized
    assert "SECRET_DRAFT" not in serialized
    types = [item[0] for item in drafts]
    if "token_delta" in types:
        verify_done = next(
            index
            for index, item in enumerate(drafts)
            if item[0] == "status"
            and item[1].get("stage") == "verify_answer"
            and item[1].get("phase") == "completed"
        )
        first_token = types.index("token_delta")
        assert first_token > verify_done


def test_mixed_route_skips_company_nodes() -> None:
    """Genuine mixed clarification never visits company-only stages."""

    query = "What is the capital of France and what is our refund period?"
    drafts, starts, terminals = _collect_route(query)
    _assert_one_start_at_most_one_terminal(starts, terminals)
    assert _MIXED_REQUIRED <= set(starts)
    assert _COMPANY_ONLY_NODES.isdisjoint(starts)
    assert "general_scope" not in starts
    assert query not in str(drafts)


def test_company_route_visits_retrieve_and_skips_direct_scopes() -> None:
    """Document questions enter company retrieve, not general/mixed."""

    hybrid = _SpyHybrid()
    query = "What is our refund period?"
    drafts, starts, terminals = _collect_route(query, hybrid=hybrid)
    _assert_one_start_at_most_one_terminal(starts, terminals)
    assert hybrid.calls >= 1
    assert _COMPANY_REQUIRED <= set(starts)
    assert "general_scope" not in starts
    assert "mixed_scope" not in starts
    assert "invalid_scope" not in starts
    assert query not in str(drafts)
    types = [item[0] for item in drafts]
    terminals_proto = [
        item[0] for item in drafts if item[0] in {"completed", "cancelled", "error", "partial"}
    ]
    assert len(terminals_proto) <= 1
    if "token_delta" in types:
        verify_done = next(
            index
            for index, item in enumerate(drafts)
            if item[0] == "status"
            and item[1].get("stage") == "verify_answer"
            and item[1].get("phase") == "completed"
        )
        assert types.index("token_delta") > verify_done


def test_invalid_route_skips_answer_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing plan fails closed on invalid_scope with no answer start."""

    def _drop_plan(state: dict[str, Any]) -> dict[str, Any]:
        """Return a planned state without a retrieval plan.

        Args:
            state: Graph state after prepare.

        Returns:
            Planned mapping with ``retrieval_plan`` cleared.
        """

        return {**state, "status": "planned", "retrieval_plan": None}

    monkeypatch.setattr(
        "smart_rag_agents.query.runtime.bound_nodes.compile_plan_node",
        _drop_plan,
    )
    drafts, starts, terminals = _collect_route("Hello")
    _assert_one_start_at_most_one_terminal(starts, terminals)
    assert _INVALID_REQUIRED <= set(starts)
    assert "general_scope" not in starts
    assert "company_scope" not in starts
    assert "generate_answer" not in starts
    assert "verify_answer" not in starts
    assert "token_delta" not in {item[0] for item in drafts}
    proto = [item[0] for item in drafts if item[0] in {"completed", "error", "partial"}]
    assert proto.count("completed") == 0
    del terminals
