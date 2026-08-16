"""Query LangGraph: admission enforcement only (Phase 6 packet 1).

Profiling, retrieval, fusion, and answering are packet 2+. Missing
``AuthorizedRuntimeContext`` fails closed. Compile constructs no sockets
or OpenAI clients.
"""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext


class QueryGraphState(TypedDict):
    """Typed query state for admission. Later packets add profile fields.

    Attributes:
        status: ``pending``, ``admitted``, or ``admission_rejected``.
        detail: Safe diagnostic text. Never an answer claim.
        authorized_runtime: Server-derived context mapping, or null.
        route_family: Copied from context when admitted.
        deadline_at: ISO-8601 deadline copied from context.
        recursion_limit: Superstep cap copied from context.
        remaining_corrections: Remaining correction slots.
        remaining_subquestions: Remaining subquestion slots.
        remaining_model_calls: Remaining counted gateway calls.
        remaining_tool_calls: Remaining tool executions.
        remaining_discovery_rounds: Remaining optional discovery rounds.
        remaining_manifests: Remaining optional manifests.
        remaining_side_effects: Remaining side-effecting tools.
        remaining_recursion_steps: Remaining LangGraph supersteps.
    """

    status: Literal["pending", "admitted", "admission_rejected"]
    detail: str
    authorized_runtime: dict[str, object] | None
    route_family: str | None
    deadline_at: str | None
    recursion_limit: int
    remaining_corrections: int
    remaining_subquestions: int
    remaining_model_calls: int
    remaining_tool_calls: int
    remaining_discovery_rounds: int
    remaining_manifests: int
    remaining_side_effects: int
    remaining_recursion_steps: int


QueryStateGraph: TypeAlias = StateGraph[
    QueryGraphState,
    None,
    QueryGraphState,
    QueryGraphState,
]
CompiledQueryGraph: TypeAlias = CompiledStateGraph[
    QueryGraphState,
    None,
    QueryGraphState,
    QueryGraphState,
]


def pending_query_state(
    authorized_runtime: dict[str, object] | None = None,
) -> QueryGraphState:
    """Return a pending graph input that does not claim retrieval success.

    Args:
        authorized_runtime: Optional server-derived context mapping.

    Returns:
        Minimal pending state for compile/invoke tests.
    """

    return {
        "status": "pending",
        "detail": "",
        "authorized_runtime": authorized_runtime,
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
        Missing or invalid context sets ``admission_rejected`` and ends.
        This node never claims an answer.

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
        "detail": "admission accepted; profiling is not implemented",
        "authorized_runtime": dumped,
        "route_family": context.route_family.value,
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


def build_query_graph() -> QueryStateGraph:
    """Construct the packet 1 query ``StateGraph`` (not yet compiled).

    Returns:
        An uncompiled graph with a single ``enforce_admission`` node.

    Notes:
        State inputs: ``QueryGraphState``.
        State outputs: admitted or admission_rejected.
        Persistence writes: none.
        External/model calls: none.
        Budget/deadline behavior: copies server ceilings; fails closed
            without authorized context.
        Failure/fallback route: ``admission_rejected`` then END.
    """

    builder: QueryStateGraph = StateGraph(
        QueryGraphState,
        input_schema=QueryGraphState,
        output_schema=QueryGraphState,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType] - upstream optional hooks use Any
        "enforce_admission",
        enforce_admission,
    )
    builder.add_edge(START, "enforce_admission")
    builder.add_edge("enforce_admission", END)
    return builder


graph: CompiledQueryGraph = build_query_graph().compile()  # pyright: ignore[reportUnknownMemberType] - upstream optional hooks use Any
"""Compiled query graph for ``langgraph.json`` registration."""
