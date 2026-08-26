"""Fail closed when the compiled plan cannot select a scope path."""

from __future__ import annotations

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState


def invalid_scope_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Fail closed when the compiled plan cannot select a scope path.

    State inputs:
        Planned or missing retrieval plan.

    State outputs:
        ``status=routing_rejected`` with no answer draft.

    Persistence writes:
        None.

    External/model calls:
        None.

    Budget/deadline behavior:
        None.

    Failure/fallback route:
        This node is the fail-closed route.

    Args:
        state: State after ``compile_plan``.
        deps: Unused.

    Returns:
        Rejected state that must not reach verification with a draft.
    """

    del deps
    if skip_closed_nodes(state):
        return state
    return {
        **state,
        "status": "routing_rejected",
        "detail": "invalid_scope_plan",
        "answer": None,
    }
