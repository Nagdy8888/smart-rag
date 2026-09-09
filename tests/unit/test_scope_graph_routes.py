"""Post-plan scope routing for company, general, mixed, and invalid paths."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.nodes.topology import route_after_plan
from smart_rag_agents.query.state import QueryGraphState, pending_query_state
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import UserRole

from tests.support.scope_graph import COMPANY_ONLY_NODES, SpyHybrid
from tests.support.typed_graph import compile_state_graph


def _visit_nodes(
    query: str,
    *,
    hybrid: SpyHybrid | None = None,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
) -> list[str]:
    """Compile and stream one admitted run, returning visited node names.

    Args:
        query: Original user text.
        hybrid: Optional Hybrid spy. ``None`` proves the path never needs it.
        requested_search_scope: Client source preference on the runtime.

    Returns:
        Node names emitted by LangGraph ``updates`` stream mode.
    """

    deps = QueryGraphDeps(hybrid_retriever=hybrid)
    compiled = compile_state_graph(build_query_graph(deps))
    state = pending_query_state(
        _runtime(requested_search_scope=requested_search_scope).model_dump(
            mode="json"
        ),
        user_query=query,
    )
    visited: list[str] = []
    for chunk in compiled.stream(state, stream_mode="updates"):
        if isinstance(chunk, dict):
            visited.extend(str(name) for name in cast(dict[object, object], chunk))
    return visited


def _runtime(
    *,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
) -> AuthorizedRuntimeContext:
    """Return a Composite admission envelope for routing tests.

    Args:
        requested_search_scope: Client source preference copied into runtime.

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
        requested_search_scope=requested_search_scope,
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


def _planned_state(query: str) -> QueryGraphState:
    """Compile a retrieval plan and store it on pending graph state.

    Args:
        query: Original user text.

    Returns:
        Planned query-graph state mapping.
    """

    runtime = _runtime()
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    state = pending_query_state(user_query=query)
    state["status"] = "planned"
    state["retrieval_plan"] = plan.model_dump(mode="json")
    return state


def test_query_graph_registers_explicit_scope_nodes() -> None:
    """The compiled topology exposes scope nodes and drops execute_branches."""

    compiled = compile_state_graph(build_query_graph())
    names = set(compiled.get_graph().nodes)
    assert "company_scope" in names
    assert "general_scope" in names
    assert "mixed_scope" in names
    assert "invalid_scope" in names
    assert "generate_answer" in names
    assert "verify_answer" in names
    assert "execute_branches" not in names


def test_greeting_and_general_plan_route_to_general_scope() -> None:
    """Greetings and world-knowledge plans skip company retrieval."""

    assert route_after_plan(_planned_state("Hello")) == "general_scope"
    assert route_after_plan(_planned_state("hi friend")) == "general_scope"
    assert (
        route_after_plan(_planned_state("What is the capital of France?"))
        == "general_scope"
    )
    assert (
        route_after_plan(_planned_state("Rewrite this paragraph: The sky is blue."))
        == "general_scope"
    )


def test_mixed_plan_routes_to_mixed_scope() -> None:
    """Genuine mixed conflict uses the clarification node."""

    query = "What is the capital of France and what is our refund period?"
    assert route_after_plan(_planned_state(query)) == "mixed_scope"


def test_company_plan_routes_to_company_scope() -> None:
    """Document questions still enter the retrieval path."""

    assert (
        route_after_plan(_planned_state("What is our refund period?"))
        == "company_scope"
    )


def test_missing_plan_is_invalid_scope() -> None:
    """A missing compiled plan fails closed instead of answering."""

    state = pending_query_state(user_query="Hello")
    state["status"] = "planned"
    assert route_after_plan(state) == "invalid_scope"
    assert route_after_plan(state) == "invalid_scope"


def test_graph_inspection_and_scoped_refusal_remain_company() -> None:
    """Inspection and scoped refusal still enter the company retrieve path."""

    assert (
        route_after_plan(_planned_state("Inspect the current graph workspace"))
        == "company_scope"
    )
    assert (
        route_after_plan(_planned_state("Describe the unlabeled chart in the figure"))
        == "company_scope"
    )


def test_general_and_mixed_paths_skip_retrievers_and_company_nodes() -> None:
    """Direct paths never call Hybrid or visit company-only nodes."""

    hybrid = SpyHybrid()
    general_nodes = _visit_nodes("Hello", hybrid=hybrid)
    assert hybrid.calls == 0
    assert "general_scope" in general_nodes
    assert "verify_answer" in general_nodes
    assert COMPANY_ONLY_NODES.isdisjoint(general_nodes)

    mixed_nodes = _visit_nodes(
        "What is the capital of France and what is our refund period?",
        hybrid=hybrid,
    )
    assert hybrid.calls == 0
    assert "mixed_scope" in mixed_nodes
    assert "verify_answer" in mixed_nodes
    assert COMPANY_ONLY_NODES.isdisjoint(mixed_nodes)


def test_mixed_scope_leaves_usage_counters_unchanged() -> None:
    """Genuine mixed clarification spends no answer or verifier calls."""

    runtime = _runtime()
    compiled = compile_state_graph(build_query_graph(QueryGraphDeps()))
    query = "What is the capital of France and what is our refund period?"
    out = compiled.invoke(
        pending_query_state(runtime.model_dump(mode="json"), user_query=query)
    )
    assert out["status"] in {"verified", "verified_partial", "refused"}
    assert out["answer_call_count"] == 0
    assert out["verifier_call_count"] == 0
    assert out["keyword_extract_count"] == 0
    assert out["catalog_llm_call_count"] == 0
    assert out["remaining_model_calls"] == runtime.model_call_ceiling


def test_successful_direct_paths_reach_verification() -> None:
    """General and mixed drafts still pass through verify_answer."""

    assert "verify_answer" in _visit_nodes("What is the capital of France?")
    assert "verify_answer" in _visit_nodes(
        "What is the capital of France and what is our refund period?"
    )


def test_company_path_visits_retrieve_then_verify() -> None:
    """Company plans still run retrieve, correction, and verification."""

    hybrid = SpyHybrid()
    nodes = _visit_nodes("What is our refund period?", hybrid=hybrid)
    assert hybrid.calls >= 1
    assert "company_scope" in nodes
    assert "apply_correction" in nodes
    assert "verify_answer" in nodes


def test_pdf_heading_company_visits_company_scope() -> None:
    """Requested Company files sends a bare heading through company retrieval."""

    hybrid = SpyHybrid()
    nodes = _visit_nodes(
        "Parallel Tool Execution",
        hybrid=hybrid,
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    assert hybrid.calls >= 1
    assert "company_scope" in nodes
    assert "general_scope" not in nodes


def test_pdf_heading_general_visits_general_scope() -> None:
    """Requested General knowledge never opens company retrieval for a heading."""

    hybrid = SpyHybrid()
    nodes = _visit_nodes(
        "Parallel Tool Execution",
        hybrid=hybrid,
        requested_search_scope=RequestedSearchScope.GENERAL_KNOWLEDGE,
    )
    assert hybrid.calls == 0
    assert "general_scope" in nodes
    assert "company_scope" not in nodes


def test_studio_graphs_use_the_same_post_plan_router() -> None:
    """Local and live Studio compile the same scope edges as production."""

    production = set(compile_state_graph(build_query_graph()).get_graph().nodes)
    local = set(
        compile_state_graph(build_query_graph(studio_local=True)).get_graph().nodes
    )
    live = set(
        compile_state_graph(build_query_graph(studio_live=True)).get_graph().nodes
    )
    for names in (production, local, live):
        assert "company_scope" in names
        assert "general_scope" in names
        assert "mixed_scope" in names
        assert "invalid_scope" in names
        assert "execute_branches" not in names
    assert "seed_studio_runtime" in local
    assert "seed_studio_live_runtime" in live


def test_pipeline_module_is_removed() -> None:
    """Packet 2 deletes the node monolith instead of leaving a shim."""

    from importlib import util
    from pathlib import Path

    pipeline = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "agents"
        / "src"
        / "smart_rag_agents"
        / "query"
        / "nodes"
        / "pipeline.py"
    )
    assert pipeline.exists() is False
    assert util.find_spec("smart_rag_agents.query.nodes.pipeline") is None
