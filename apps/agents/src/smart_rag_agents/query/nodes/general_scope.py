"""Direct general, greeting, user-text, and degraded answers without retrieve."""

from __future__ import annotations

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.answer import generate_answer_node
from smart_rag_agents.query.state import QueryGraphState


def general_scope_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Answer general, greeting, user-text, or degraded plans without retrieve.

    State inputs:
        Planned NoRetrieval general/user-text state.

    State outputs:
        One general or user-text answer draft.

    Persistence writes:
        Counted ``usage_kind=answer`` when a gateway is bound.

    External/model calls:
        Zero or one general-chat call. Never retrieval or a verifier model.

    Budget/deadline behavior:
        Same answer reservation as company generation.

    Failure/fallback route:
        Gateway failure is verified partial, never fabricated success.

    Args:
        state: State after ``compile_plan``.
        deps: Gateway and prompt bindings.

    Returns:
        Answered state ready for deterministic verification.
    """

    return generate_answer_node(state, deps)
