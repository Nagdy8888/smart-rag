"""Apply at most one global retrieval correction after company branches."""

from __future__ import annotations

from typing import cast

from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.correction import (
    apply_correction_to_plan,
    decide_correction,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import BranchResult
from smart_rag_core.query_routing.serde import (
    branch_results_from_state,
    plan_from_state,
    preparation_from_state,
)

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import (
    retrieve_budget,
    runtime_from_state,
    skip_closed_nodes,
)
from smart_rag_agents.query.nodes.tokens import accumulated_tokens
from smart_rag_agents.query.state import QueryGraphState


def apply_correction_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Apply at most one global correction, then end without answering.

    State inputs:
        plan, preparation, branch results, remaining_corrections,
        correction_applied.

    State outputs:
        ``correction``, possibly extra branch results, ``corrected_route``,
        ``remaining_model_calls`` after any extra retrieve, and
        ``insufficient_evidence`` when exhausted.

    Persistence writes:
        None. ``routing_correction`` is stored on graph state for packet 3.

    External/model calls:
        At most one extra Combined or same-route retrieve. Never both.
        Never a correction loop.

    Budget/deadline behavior:
        Consumes the single remaining correction slot. Combined escalation
        is skipped when the reserved envelope cannot enlarge.

    Failure/fallback route:
        Exhaustion is verified partial/insufficient evidence, not an answer.
        Historical relationships cannot take a graph path.

    Args:
        state: State after branch execution.
        deps: Retrievers for the optional extra branch.

    Returns:
        State after the single correction. Packet 3 nodes follow.
    """

    if skip_closed_nodes(state):
        return state
    if state.get("retrieval_plan") is None or state.get("preparation") is None:
        return state
    context = runtime_from_state(state)
    if context is None:
        return state
    try:
        prep = preparation_from_state(state["preparation"])
        plan = plan_from_state(state["retrieval_plan"])
        results = branch_results_from_state(state.get("branch_results"))
    except ValueError as exc:
        return cast(
            QueryGraphState,
            {
                **state,
                "status": "routing_rejected",
                "detail": str(exc) or "invalid_correction_state",
            },
        )
    already = bool(state.get("correction_applied"))
    try:
        decision = decide_correction(
            plan,
            prep,
            results,
            runtime=context,
            remaining_corrections=state["remaining_corrections"],
            already_applied=already,
        )
    except QueryRoutingError as exc:
        return cast(
            QueryGraphState,
            {
                **state,
                "status": "routing_rejected",
                "detail": exc.reason,
            },
        )
    extra: list[BranchResult] = []
    updated = plan
    query_budget = retrieve_budget(state, context)
    if decision.applied:
        updated = apply_correction_to_plan(plan, prep, decision, results)
        new_specs = updated.branches[len(plan.branches) :]
        if new_specs:
            extra_plan = updated.model_copy(update={"branches": new_specs})
            try:
                extra = list(
                    execute_branches(
                        extra_plan,
                        prep,
                        context,
                        hybrid_retriever=deps.hybrid_retriever,
                        graph_retriever=deps.graph_retriever,
                        table_executor=deps.table_executor,
                        query_budget=query_budget,
                        cancel_check=deps.cancel_check,
                    )
                )
            except QueryRoutingError as exc:
                return cast(
                    QueryGraphState,
                    {
                        **state,
                        "status": "insufficient_evidence",
                        "detail": exc.reason,
                        "correction": decision.model_dump(mode="json"),
                        "remaining_corrections": decision.remaining_corrections,
                        "correction_applied": True,
                        "remaining_model_calls": query_budget.remaining_model_calls,
                    },
                )
    combined = (*results, *extra)
    terminal = "correction_applied"
    detail = "one correction applied; fusion and answering follow"
    if not decision.applied:
        detail = "no correction; fusion and answering follow"
    if decision.exhausted_status == "insufficient_evidence":
        terminal = "insufficient_evidence"
        detail = "insufficient evidence; verified partial follows"
    whole_refused = any(
        item.fallback_reason == "section_coverage_below_1" for item in combined
    )
    if whole_refused:
        terminal = "insufficient_evidence"
        detail = "section_coverage_ratio below 1.0; scoped refusal"
    return cast(
        QueryGraphState,
        {
            **state,
            "status": terminal,
            "detail": detail,
            "retrieval_plan": updated.model_dump(mode="json"),
            "branch_results": [item.model_dump(mode="json") for item in combined],
            "correction": decision.model_dump(mode="json"),
            "corrected_route": updated.corrected_route.value
            if updated.corrected_route is not None
            else None,
            "effective_route": updated.effective_route.value,
            "remaining_corrections": decision.remaining_corrections,
            "correction_applied": decision.applied or already,
            "keyword_extract_count": sum(
                item.keyword_extract_count for item in combined
            ),
            "catalog_llm_call_count": 0,
            "remaining_model_calls": query_budget.remaining_model_calls,
            **accumulated_tokens(
                state, query_budget.prompt_tokens, query_budget.completion_tokens
            ),
        },
    )
