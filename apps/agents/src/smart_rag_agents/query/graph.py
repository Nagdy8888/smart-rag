"""Query LangGraph: admission, memory, preparation, routing, retrieve, one correction.

Packet 3 owns Combined fusion, answer generation, and the verifier. This
module compiles without sockets or OpenAI clients.
"""

from __future__ import annotations

from typing import cast

from langgraph.graph import END, START, StateGraph
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes import (
    apply_correction_node,
    compile_plan_node,
    execute_branches_node,
    load_memory_node,
    prepare_query_node,
)
from smart_rag_agents.query.state import (
    CompiledQueryGraph,
    QueryGraphState,
    QueryStateGraph,
    pending_query_state,
)

__all__ = [
    "CompiledQueryGraph",
    "QueryGraphState",
    "QueryStateGraph",
    "build_query_graph",
    "enforce_admission",
    "graph",
    "pending_query_state",
]


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


def _route_after_admission(state: QueryGraphState) -> str:
    """Continue past admission only when context was valid.

    Args:
        state: State after ``enforce_admission``.

    Returns:
        ``load_memory`` or ``end``.
    """

    if state["status"] == "admission_rejected":
        return "end"
    return "load_memory"


def _route_after_prepare(state: QueryGraphState) -> str:
    """Stop on routing rejection after preparation.

    Args:
        state: State after ``prepare_query``.

    Returns:
        ``compile_plan`` or ``end``.
    """

    if state["status"] in {"admission_rejected", "routing_rejected"}:
        return "end"
    return "compile_plan"


def build_query_graph(deps: QueryGraphDeps | None = None) -> QueryStateGraph:
    """Construct the packet 2 query ``StateGraph`` (not yet compiled).

    Args:
        deps: Optional retrieve/memory bindings. Default compiles without
            sockets or OpenAI clients.

    Returns:
        An uncompiled graph: admission → memory → prepare → plan →
        branches → one correction → END.

    Notes:
        State inputs: ``QueryGraphState``.
        State outputs: routed retrieve diagnostics, never an answer.
        Persistence writes: counted prep consume when a model is used.
        External/model calls: at most one prep call plus retrievers.
        Budget/deadline behavior: copies server ceilings; never enlarges.
        Failure/fallback route: ``admission_rejected`` / ``routing_rejected``
            / ``insufficient_evidence`` then END.
    """

    bound = deps or QueryGraphDeps()
    builder: QueryStateGraph = StateGraph(
        QueryGraphState,
        input_schema=QueryGraphState,
        output_schema=QueryGraphState,
    )

    def load_memory(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for bounded memory load.

        Args:
            state: Admitted state.

        Returns:
            State with memory records.
        """

        return load_memory_node(state, bound)

    def prepare_query(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for typed preparation.

        Args:
            state: State after memory load.

        Returns:
            State with preparation.
        """

        return prepare_query_node(state, bound)

    def compile_plan(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for the route matrix.

        Args:
            state: Prepared state.

        Returns:
            State with a retrieval plan.
        """

        return compile_plan_node(state)

    def execute_branches(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for bounded retrieve branches.

        Args:
            state: Planned state.

        Returns:
            State with branch results.
        """

        return execute_branches_node(state, bound)

    def apply_correction(state: QueryGraphState) -> QueryGraphState:
        """LangGraph wrapper for the single global correction.

        Args:
            state: State after branches.

        Returns:
            Terminal packet-2 state.
        """

        return apply_correction_node(state, bound)

    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "enforce_admission",
        enforce_admission,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "load_memory",
        load_memory,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "prepare_query",
        prepare_query,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "compile_plan",
        compile_plan,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "execute_branches",
        execute_branches,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType]
        "apply_correction",
        apply_correction,
    )
    builder.add_edge(START, "enforce_admission")
    builder.add_conditional_edges(
        "enforce_admission",
        _route_after_admission,
        {"load_memory": "load_memory", "end": END},
    )
    builder.add_edge("load_memory", "prepare_query")
    builder.add_conditional_edges(
        "prepare_query",
        _route_after_prepare,
        {"compile_plan": "compile_plan", "end": END},
    )
    builder.add_edge("compile_plan", "execute_branches")
    builder.add_edge("execute_branches", "apply_correction")
    builder.add_edge("apply_correction", END)
    return builder


graph: CompiledQueryGraph = build_query_graph().compile()  # pyright: ignore[reportUnknownMemberType]
"""Compiled query graph for ``langgraph.json`` registration."""
