"""Emit genuine mixed-scope clarification without retrieval or models."""

from __future__ import annotations

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.answer import generate_answer_node
from smart_rag_agents.query.state import QueryGraphState


def mixed_scope_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Emit genuine mixed-scope clarification without retrieval or models.

    State inputs:
        Planned NoRetrieval clarification state.

    State outputs:
        Deterministic clarification draft. ``answer_call_count`` stays 0.

    Persistence writes:
        None.

    External/model calls:
        None.

    Budget/deadline behavior:
        No model spend.

    Failure/fallback route:
        Closed states pass through.

    Args:
        state: State after ``compile_plan``.
        deps: Unused except closed-state guards.

    Returns:
        Clarification draft for deterministic verification.
    """

    return generate_answer_node(state, deps)
