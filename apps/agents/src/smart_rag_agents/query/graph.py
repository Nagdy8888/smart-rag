"""Foundation query graph scaffold for LangGraph configuration qualification.

This module intentionally does not perform retrieval, routing, answering, or
budget enforcement. Invocation only records that the Phase 1 foundation graph
is unconfigured for business work.
"""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class QueryFoundationState(TypedDict):
    """Minimal state for the Phase 1 query graph scaffold.

    Attributes:
        status: Always ``unconfigured`` for foundation qualification.
        detail: Human-readable explanation that business query work is absent.
    """

    status: Literal["unconfigured"]
    detail: str


QueryStateGraph: TypeAlias = StateGraph[
    QueryFoundationState,
    None,
    QueryFoundationState,
    QueryFoundationState,
]
CompiledQueryGraph: TypeAlias = CompiledStateGraph[
    QueryFoundationState,
    None,
    QueryFoundationState,
    QueryFoundationState,
]


def mark_unconfigured(state: QueryFoundationState) -> QueryFoundationState:
    """Return an honest unconfigured status without claiming query success.

    Args:
        state: Incoming foundation state (ignored for business fields).

    Returns:
        State with ``status`` set to ``unconfigured`` and an explanatory detail.

    Side Effects:
        None. No model calls, persistence writes, or external I/O.

    Failure / Fallback:
        This node cannot fail for missing infrastructure; it is the degraded
        foundation path until later phases implement real query nodes.
    """

    return {
        "status": "unconfigured",
        "detail": (
            "Phase 1 query graph scaffold only; retrieval and answering are "
            "not implemented."
        ),
    }


def build_query_graph() -> QueryStateGraph:
    """Construct the foundation query ``StateGraph`` (not yet compiled).

    Returns:
        An uncompiled ``StateGraph`` with a single unconfigured marker node.

    Notes:
        State inputs: ``QueryFoundationState``.
        State outputs: same shape with ``status=unconfigured``.
        Persistence writes: none.
        External/model calls: none.
        Budget/deadline behavior: none (foundation only).
        Failure/fallback route: always marks unconfigured.
    """

    builder: QueryStateGraph = StateGraph(
        QueryFoundationState,
        input_schema=QueryFoundationState,
        output_schema=QueryFoundationState,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType] - upstream optional hooks use Any
        "mark_unconfigured",
        mark_unconfigured,
    )
    builder.add_edge(START, "mark_unconfigured")
    builder.add_edge("mark_unconfigured", END)
    return builder


graph: CompiledQueryGraph = build_query_graph().compile()  # pyright: ignore[reportUnknownMemberType] - upstream optional hooks use Any
"""Compiled foundation query graph for ``langgraph.json`` registration."""
