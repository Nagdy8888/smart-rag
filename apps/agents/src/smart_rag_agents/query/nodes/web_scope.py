"""Fail-closed Web research node until the P06-41 executor is bound."""

from __future__ import annotations

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState


def web_scope_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Return a typed Web fail-closed state without company retrieval.

    State inputs:
        Planned ``web_research`` retrieval plan. Never company passages.

    State outputs:
        ``status=routing_rejected`` with ``web_search_disabled`` or
        ``web_search_unconfigured``. No answer draft.

    Persistence writes:
        None.

    External/model calls:
        None. This packet does not bind Exa or crawl-proxy.

    Budget/deadline behavior:
        No model or tool spend.

    Failure/fallback route:
        Truthful fail-closed. Never Hybrid, general chat, or company
        retrieval. P06-41 replaces the enabled path.

    Args:
        state: State after ``compile_plan``.
        deps: Web enablement flags. No executor is bound in this packet.

    Returns:
        Rejected state that must not reach verification with a draft.
    """

    if skip_closed_nodes(state):
        return state
    detail = "web_search_disabled"
    if deps.web_search_enabled and not deps.web_search_configured:
        detail = "web_search_unconfigured"
    return {
        **state,
        "status": "routing_rejected",
        "detail": detail,
        "answer": None,
    }
