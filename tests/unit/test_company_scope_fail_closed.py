"""Company-scope and memory nodes fail closed instead of crashing the stream."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.company_scope import company_scope_node
from smart_rag_agents.query.nodes.memory import load_memory_node
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.retrieval.fusion import FusionError
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import UserRole


def _runtime() -> AuthorizedRuntimeContext:
    """Return a company admission envelope for fail-closed tests.

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
        requested_search_scope=RequestedSearchScope.AUTO,
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


def test_company_scope_hybrid_fusion_error_is_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hybrid RRF FusionError degrades to insufficient_evidence, not a crash."""

    runtime = _runtime()
    prep = prepare_query(
        "In the company document, what HELM score does GPT-5 mini receive?",
        runtime=runtime,
    )
    plan = compile_retrieval_plan(prep, runtime)
    state = pending_query_state(
        runtime.model_dump(mode="json"),
        user_query="In the company document, what HELM score does GPT-5 mini receive?",
    )
    state["status"] = "planned"
    state["preparation"] = prep.model_dump(mode="json")
    state["retrieval_plan"] = plan.model_dump(mode="json")
    state["remaining_model_calls"] = 8
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.company_scope.execute_branches",
        MagicMock(side_effect=FusionError("more_than_three_variants")),
    )
    result = company_scope_node(state, QueryGraphDeps())
    assert result["status"] == "insufficient_evidence"
    assert "more_than_three_variants" in str(result.get("detail") or "")
    assert result.get("branch_results") == []


def test_load_memory_store_get_failure_keeps_db_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A store_get exception does not abort memory load after DB records."""

    record = MagicMock()
    record.model_dump = MagicMock(
        return_value={
            "message_id": "m1",
            "role": "user",
            "content": "hi",
            "created_at": "1970-01-01T00:00:00+00:00",
            "delimited": "<<memory>>hi<</memory>>",
        }
    )
    monkeypatch.setattr(
        "smart_rag_agents.query.nodes.memory.load_authorized_memory",
        MagicMock(return_value=[record]),
    )
    deps = QueryGraphDeps(
        connection=MagicMock(),
        store_get=MagicMock(side_effect=RuntimeError("store_down")),
    )
    runtime = _runtime()
    state = pending_query_state(
        runtime.model_dump(mode="json"),
        user_query="hello",
    )
    state["status"] = "admitted"
    result = load_memory_node(state, deps)
    assert result["status"] == "memory_loaded"
    assert result["memory_records"]
