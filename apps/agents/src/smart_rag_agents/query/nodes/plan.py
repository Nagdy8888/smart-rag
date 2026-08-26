"""Compile the deterministic retrieval plan after query preparation."""

from __future__ import annotations

from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.serde import preparation_from_state

from smart_rag_agents.query.nodes.shared import runtime_from_state, skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState


def compile_plan_node(state: QueryGraphState) -> QueryGraphState:
    """Compile the deterministic route/limitation matrix.

    State inputs:
        ``preparation``, ``authorized_runtime``, ``requested_manual_route``.

    State outputs:
        ``retrieval_plan``, ``requested_route``, ``effective_route``.

    Persistence writes:
        None. Packet 7 owns durable checkpoints.

    External/model calls:
        None. Catalog-search LLMs are forbidden.

    Budget/deadline behavior:
        Effective family is clamped to the reserved envelope.

    Failure/fallback route:
        Production manual override and fourth subquestion reject the run.

    Args:
        state: State after preparation.

    Returns:
        State with a frozen retrieval plan mapping.
    """

    if skip_closed_nodes(state) or state.get("preparation") is None:
        return state
    context = runtime_from_state(state)
    if context is None:
        return {**state, "status": "admission_rejected"}
    try:
        prep = preparation_from_state(state["preparation"])
    except ValueError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": str(exc) or "invalid_preparation",
        }
    try:
        plan = compile_retrieval_plan(
            prep,
            context,
            requested_manual_route=state.get("requested_manual_route"),
        )
    except QueryRoutingError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": exc.reason,
        }
    return {
        **state,
        "status": "planned",
        "retrieval_plan": plan.model_dump(mode="json"),
        "requested_route": plan.requested_route.value,
        "effective_route": plan.effective_route.value,
        "corrected_route": None,
        "knowledge_scope": plan.knowledge_scope.value,
        "no_retrieval_answer_mode": (
            None
            if plan.no_retrieval_answer_mode is None
            else plan.no_retrieval_answer_mode.value
        ),
        "scope_degradation_reason": (
            None
            if plan.scope_degradation_reason is None
            else plan.scope_degradation_reason.value
        ),
        "catalog_llm_call_count": 0,
        "detail": "retrieval plan compiled; answering is not implemented",
    }
