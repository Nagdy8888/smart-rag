"""Compatibility release stage: verified answers are immutable."""

from __future__ import annotations

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.state import QueryGraphState


def organize_answer_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Pass the checked release artifact through without rewriting it.

    The graph and SSE stage name remain stable for existing clients and
    checkpoints. Prose, native blocks, paragraph IDs, and persisted citation
    mappings must stay exactly as the verifier released them. Presentation
    belongs to the structured renderer, never another model call.

    Args:
        state: State containing the final checked answer and verification.
        deps: Legacy dependency argument, deliberately unused.

    Returns:
        The same state. No provider calls, persistence, or budget changes.
    """
    del deps
    return state
