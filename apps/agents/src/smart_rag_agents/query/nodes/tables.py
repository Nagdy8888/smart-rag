"""Compose StructuredTable sandbox results as a separate evidence type."""

from __future__ import annotations

from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.tables import compose_tables
from smart_rag_core.query_routing.serde import branch_results_from_state

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState


def compose_tables_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Compose StructuredTable sandbox results as a separate evidence type.

    State inputs:
        ``branch_results`` after fusion.

    State outputs:
        ``table_composition`` with exact cell/range provenance.

    Persistence writes:
        None.

    External/model calls:
        None. The answer model must not calculate totals from prose.

    Budget/deadline behavior:
        No reservation consume.

    Failure/fallback route:
        Missing ranges or prose arithmetic fail closed.

    Args:
        state: State after fusion.
        deps: Unused.

    Returns:
        State with table composition.
    """

    del deps
    if skip_closed_nodes(state):
        return state
    try:
        results = branch_results_from_state(state.get("branch_results"))
        composition = compose_tables(results)
    except AnswerError as exc:
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": exc.reason,
            "table_composition": None,
        }
    return {
        **state,
        "status": "tables_composed",
        "detail": "deterministic table provenance composed",
        "table_composition": composition.model_dump(mode="json"),
    }
