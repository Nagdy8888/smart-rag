"""Foundation ingestion graph scaffold for LangGraph configuration qualification.

This module intentionally does not parse files, embed content, update indexes,
or claim ingestion completion. Invocation only records that the Phase 1
foundation graph is unconfigured for business work.
"""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class IngestionFoundationState(TypedDict):
    """Minimal state for the Phase 1 ingestion graph scaffold.

    Attributes:
        status: Always ``unconfigured`` for foundation qualification.
        detail: Human-readable explanation that business ingestion is absent.
    """

    status: Literal["unconfigured"]
    detail: str


IngestionStateGraph: TypeAlias = StateGraph[
    IngestionFoundationState,
    None,
    IngestionFoundationState,
    IngestionFoundationState,
]
CompiledIngestionGraph: TypeAlias = CompiledStateGraph[
    IngestionFoundationState,
    None,
    IngestionFoundationState,
    IngestionFoundationState,
]


def mark_unconfigured(state: IngestionFoundationState) -> IngestionFoundationState:
    """Return an honest unconfigured status without claiming ingestion success.

    Args:
        state: Incoming foundation state (ignored for business fields).

    Returns:
        State with ``status`` set to ``unconfigured`` and an explanatory detail.

    Side Effects:
        None. No queue claims, Storage I/O, model calls, or index writes.

    Failure / Fallback:
        This node cannot fail for missing infrastructure; it is the degraded
        foundation path until later phases implement real ingestion nodes.
    """

    return {
        "status": "unconfigured",
        "detail": (
            "Phase 1 ingestion graph scaffold only; parsing and indexing are "
            "not implemented."
        ),
    }


def build_ingestion_graph() -> IngestionStateGraph:
    """Construct the foundation ingestion ``StateGraph`` (not yet compiled).

    Returns:
        An uncompiled ``StateGraph`` with a single unconfigured marker node.

    Notes:
        State inputs: ``IngestionFoundationState``.
        State outputs: same shape with ``status=unconfigured``.
        Persistence writes: none.
        External/model calls: none.
        Budget/deadline behavior: none (foundation only).
        Failure/fallback route: always marks unconfigured.
    """

    builder: IngestionStateGraph = StateGraph(
        IngestionFoundationState,
        input_schema=IngestionFoundationState,
        output_schema=IngestionFoundationState,
    )
    builder.add_node(  # pyright: ignore[reportUnknownMemberType] - upstream optional hooks use Any
        "mark_unconfigured",
        mark_unconfigured,
    )
    builder.add_edge(START, "mark_unconfigured")
    builder.add_edge("mark_unconfigured", END)
    return builder


graph: CompiledIngestionGraph = build_ingestion_graph().compile()  # pyright: ignore[reportUnknownMemberType] - upstream optional hooks use Any
"""Compiled foundation ingestion graph for ``langgraph.json`` registration."""
