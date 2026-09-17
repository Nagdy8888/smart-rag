"""Unit tests for the single global routing correction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.correction import (
    apply_correction_to_plan,
    decide_correction,
    refuse_second_correction,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchResult,
    CorrectionDecision,
    CorrectionKind,
)
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.security.identity import CallerContext, UserRole


def _runtime(
    family: Phase6RouteFamily = Phase6RouteFamily.COMPOSITE,
) -> AuthorizedRuntimeContext:
    """Build an authorized runtime for correction tests.

    Args:
        family: Reserved envelope family.

    Returns:
        Frozen packet 1 context.
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
        route_family=family,
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
        payload_hash="c" * 64,
        status="pending",
    )


def _hybrid_result(
    runtime: AuthorizedRuntimeContext,
    *,
    coverage: float,
    query: str,
) -> BranchResult:
    """Build one Hybrid branch result with a coverage score.

    Args:
        runtime: Packet 1 context.
        coverage: coverage_score to attach.
        query: Query text.

    Returns:
        Hybrid branch result.
    """

    return BranchResult(
        branch_id="hyb-0",
        kind=BranchKind.HYBRID,
        family=Phase6RouteFamily.HYBRID,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        query_text=query,
        ranked_ids=(str(uuid4()),),
        coverage_score=coverage,
        status="ok",
    )


def test_hybrid_to_combined_when_relationship_retained() -> None:
    """Weak Hybrid with a retained current relationship escalates once."""

    runtime = _runtime()
    query = "maybe related to INV-SR-1001"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.relationship_signal_retained is True
    decision = decide_correction(
        plan,
        prep,
        (_hybrid_result(runtime, coverage=0.40, query=query),),
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert decision.applied is True
    assert decision.kind is CorrectionKind.HYBRID_TO_COMBINED
    assert decision.routing_correction == "hybrid_to_combined"
    assert decision.remaining_corrections == 0
    updated = apply_correction_to_plan(
        plan,
        prep,
        decision,
        (_hybrid_result(runtime, coverage=0.40, query=query),),
    )
    assert updated.corrected_route is Phase6RouteFamily.COMBINED
    assert any(branch.kind is BranchKind.GRAPH_HYBRID for branch in updated.branches)
    assert any(branch.reuse_hybrid_ranked_ids for branch in updated.branches)


def test_same_route_retry_without_relationship() -> None:
    """Weak evidence without a relationship signal retries the same route once."""

    runtime = _runtime()
    query = "What is the status of INV-SR-1001?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    decision = decide_correction(
        plan,
        prep,
        (_hybrid_result(runtime, coverage=0.20, query=query),),
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert decision.applied is True
    assert decision.kind is CorrectionKind.SAME_ROUTE_RETRY
    updated = apply_correction_to_plan(
        plan,
        prep,
        decision,
        (_hybrid_result(runtime, coverage=0.20, query=query),),
    )
    assert any(branch.branch_id == "corr-retry" for branch in updated.branches)
    retry = next(branch for branch in updated.branches if branch.branch_id == "corr-retry")
    assert retry.query_text != query
    assert retry.bypass_retrieval_cache is True
    assert decision.alternate_query == retry.query_text


def test_identical_cached_retry_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one correction cannot replay the cached ranking query."""

    runtime = _runtime()
    query = "What is the status of INV-SR-1001?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    monkeypatch.setattr(
        "smart_rag_core.query_routing.correction.alternate_retry_query",
        lambda _prep, _cached: None,
    )
    decision = decide_correction(
        plan,
        prep,
        (_hybrid_result(runtime, coverage=0.20, query=query),),
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert decision.applied is False
    assert decision.reason == "identical_retry_rejected"
    assert decision.exhausted_status == "insufficient_evidence"
    forged = CorrectionDecision(
        applied=True,
        kind=CorrectionKind.SAME_ROUTE_RETRY,
        reason="coverage_below_threshold_same_route",
        remaining_corrections=0,
        already_applied=True,
        alternate_query=None,
    )
    with pytest.raises(QueryRoutingError, match="identical_retry"):
        apply_correction_to_plan(
            plan,
            prep,
            forged,
            (_hybrid_result(runtime, coverage=0.20, query=query),),
        )


def test_no_second_correction() -> None:
    """A second correction or loop fails closed."""

    runtime = _runtime()
    query = "What is the status of INV-SR-1001?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    results = (_hybrid_result(runtime, coverage=0.20, query=query),)
    first = decide_correction(
        plan,
        prep,
        results,
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert first.applied is True
    with pytest.raises(QueryRoutingError, match="correction_loop"):
        decide_correction(
            plan,
            prep,
            results,
            runtime=runtime,
            remaining_corrections=1,
            already_applied=True,
        )
    with pytest.raises(QueryRoutingError, match="second_correction"):
        refuse_second_correction(True)
    exhausted = decide_correction(
        plan,
        prep,
        results,
        runtime=runtime,
        remaining_corrections=0,
        already_applied=False,
    )
    assert exhausted.applied is False
    assert exhausted.exhausted_status == "insufficient_evidence"


def test_historical_cannot_escalate_to_graph() -> None:
    """Historical relationship correction cannot add a graph path."""

    runtime = _runtime()
    query = "Which team owns the widget after the handoff as of 2020-01-01?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    decision = decide_correction(
        plan,
        prep,
        (_hybrid_result(runtime, coverage=0.20, query=query),),
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert decision.kind is not CorrectionKind.HYBRID_TO_COMBINED
    updated = apply_correction_to_plan(
        plan,
        prep,
        decision,
        (_hybrid_result(runtime, coverage=0.20, query=query),),
    )
    assert not any(
        branch.kind
        in {
            BranchKind.GRAPH_LOCAL,
            BranchKind.GRAPH_HYBRID,
            BranchKind.GRAPH_GLOBAL_STEERING,
        }
        for branch in updated.branches
    )


def test_holdout_threshold_override_rejected() -> None:
    """Packet 2 refuses a holdout-driven coverage threshold change."""

    runtime = _runtime()
    query = "What is the status of INV-SR-1001?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    with pytest.raises(QueryRoutingError, match="holdout_driven_threshold_change"):
        decide_correction(
            plan,
            prep,
            (_hybrid_result(runtime, coverage=0.20, query=query),),
            runtime=runtime,
            remaining_corrections=1,
            already_applied=False,
            coverage_threshold_override=0.40,
        )


def test_coverage_above_threshold_skips_correction() -> None:
    """Strong Hybrid coverage does not spend the correction budget."""

    runtime = _runtime()
    query = "maybe related to INV-SR-1001"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    decision = decide_correction(
        plan,
        prep,
        (_hybrid_result(runtime, coverage=0.90, query=query),),
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert decision.applied is False
    assert decision.kind is CorrectionKind.NONE
    assert decision.remaining_corrections == 1


def test_hybrid_envelope_blocks_combined_escalation() -> None:
    """A Hybrid reservation cannot be enlarged by Hybrid-to-Combined."""

    runtime = _runtime(Phase6RouteFamily.HYBRID)
    query = "maybe related to INV-SR-1001"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    decision = decide_correction(
        plan,
        prep,
        (_hybrid_result(runtime, coverage=0.40, query=query),),
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert decision.applied is False
    assert decision.kind is CorrectionKind.NONE
    assert decision.exhausted_status == "insufficient_evidence"
    assert decision.reason == "escalation_envelope_blocked"


class _FakeHybrid:
    """Test double returning a weak coverage Hybrid result."""

    query_budget: QueryRetrieveBudget | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> object:
        """Return a weak Hybrid payload.

        Args:
            query: Branch query.
            caller: Unused caller.
            profile: Unused profile.
            deadline_seconds: Unused slice.

        Returns:
            Simple namespace matching HybridRunResult fields used here.
        """

        del caller, profile, deadline_seconds
        return SimpleNamespace(
            ranked_ids=(UUID("00000000-0000-0000-0000-000000000001"),),
            coverage=SimpleNamespace(
                coverage_score=0.40,
                uncovered_headings=(),
                signal="weak_evidence",
                notes=(),
            ),
            fallback_reason="none",
        )


def test_execute_then_one_correction_reuses_hybrid_ids() -> None:
    """The Combined correction branch reuses Hybrid ranked IDs."""

    runtime = _runtime()
    query = "maybe related to INV-SR-1001"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    results = execute_branches(plan, prep, runtime, hybrid_retriever=_FakeHybrid())
    decision = decide_correction(
        plan,
        prep,
        results,
        runtime=runtime,
        remaining_corrections=1,
        already_applied=False,
    )
    assert decision.kind is CorrectionKind.HYBRID_TO_COMBINED
    updated = apply_correction_to_plan(plan, prep, decision, results)
    combined = [
        branch for branch in updated.branches if branch.branch_id == "corr-combined"
    ]
    assert combined
    assert combined[0].reuse_hybrid_ranked_ids == (
        "00000000-0000-0000-0000-000000000001",
    )


def test_insufficient_evidence_after_correction_ends() -> None:
    """Exhausted retrieval after correction routes to END, not fusion."""

    from smart_rag_agents.query.nodes.topology import route_after_correction
    from smart_rag_agents.query.state import pending_query_state

    state = pending_query_state()
    state["status"] = "insufficient_evidence"
    assert route_after_correction(state) == "end"
    state["status"] = "correction_applied"
    assert route_after_correction(state) == "fuse_evidence"


def test_post_correction_coverage_is_recomputed_before_answer() -> None:
    """A retry that stays below 0.65 cannot proceed to answer generation."""

    from smart_rag_agents.query.deps import QueryGraphDeps
    from smart_rag_agents.query.nodes.correction import apply_correction_node
    from smart_rag_agents.query.state import pending_query_state

    runtime = _runtime()
    query = "What is the status of INV-SR-1001?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    results = (_hybrid_result(runtime, coverage=0.20, query=query),)
    state = pending_query_state(runtime.model_dump(mode="json"), user_query=query)
    state["status"] = "retrieved"
    state["remaining_corrections"] = 1
    state["remaining_model_calls"] = 6
    state["retrieval_plan"] = plan.model_dump(mode="json")
    state["preparation"] = prep.model_dump(mode="json")
    state["branch_results"] = [item.model_dump(mode="json") for item in results]
    out = apply_correction_node(state, QueryGraphDeps(hybrid_retriever=_FakeHybrid()))
    assert out["status"] == "insufficient_evidence"
    assert out["detail"] == "coverage_below_threshold_after_correction"
    assert plan.knowledge_scope.value != "general_knowledge"
