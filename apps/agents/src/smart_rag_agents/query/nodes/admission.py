"""Copy server-assigned admission ceilings into query-graph state."""

from __future__ import annotations

from typing import cast

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext

from smart_rag_agents.query.state import QueryGraphState


def enforce_admission(state: QueryGraphState) -> QueryGraphState:
    """Require ``AuthorizedRuntimeContext`` and copy server ceilings into state.

    State inputs:
        ``authorized_runtime`` mapping produced by FastAPI/core, or null.

    State outputs:
        ``status=admitted`` with ceiling counters copied from context, or
        ``status=admission_rejected`` with no retrieval/answer claim.

    Persistence writes:
        None. Durable admit already happened in FastAPI/core.

    External/model calls:
        None.

    Budget/deadline behavior:
        Copies server-assigned deadline and remaining ceilings. Does not
        enlarge them. Client role, BM25, graph, cache, and Valkey fields in
        extra mapping keys are ignored by Pydantic ``extra=forbid``.

    Failure/fallback route:
        Missing or invalid context sets ``admission_rejected`` and later
        nodes pass through to END. This node never claims an answer.

    Args:
        state: Incoming query graph state.

    Returns:
        State with admission status and copied ceilings.
    """

    rejected: QueryGraphState = {
        **state,
        "status": "admission_rejected",
        "detail": "authorized runtime context missing or invalid",
        "route_family": None,
        "deadline_at": None,
        "recursion_limit": 0,
        "remaining_corrections": 0,
        "remaining_subquestions": 0,
        "remaining_model_calls": 0,
        "remaining_tool_calls": 0,
        "remaining_discovery_rounds": 0,
        "remaining_manifests": 0,
        "remaining_side_effects": 0,
        "remaining_recursion_steps": 0,
    }
    raw = state.get("authorized_runtime")
    try:
        context = AuthorizedRuntimeContext.from_mapping(raw)
    except (ValueError, TypeError):
        return rejected

    dumped = cast(dict[str, object], context.model_dump(mode="json"))
    deadline = context.deadline_at.isoformat()
    return {
        **state,
        "status": "admitted",
        "detail": "admission accepted",
        "authorized_runtime": dumped,
        "route_family": context.route_family.value,
        "requested_route": context.route_family.value,
        "requested_search_scope": context.requested_search_scope.value,
        "deadline_at": deadline,
        "recursion_limit": context.recursion_limit,
        "remaining_corrections": context.correction_ceiling,
        "remaining_subquestions": context.subquestion_ceiling,
        "remaining_model_calls": context.model_call_ceiling,
        "remaining_tool_calls": context.tool_ceiling,
        "remaining_discovery_rounds": context.discovery_ceiling,
        "remaining_manifests": context.manifest_ceiling,
        "remaining_side_effects": context.side_effect_ceiling,
        "remaining_recursion_steps": context.recursion_limit,
    }
