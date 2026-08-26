"""Company-scope retrieval after a validated company ``RetrievalPlan``."""

from __future__ import annotations

from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.serde import plan_from_state, preparation_from_state

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import (
    retrieve_budget,
    runtime_after_retrieve_budget,
    runtime_from_state,
    skip_closed_nodes,
)
from smart_rag_agents.query.state import QueryGraphState


def company_scope_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Run bounded parallel retrieval branches without fusion or answering.

    State inputs:
        ``retrieval_plan``, ``preparation``, ``authorized_runtime``,
        ``remaining_model_calls``.

    State outputs:
        ``branch_results``, keyword/catalog counters (must stay 0),
        ``remaining_model_calls`` after retrieve-time embed/rerank/LightRAG,
        and ``authorized_runtime`` with the post-retrieve reservation
        version.

    Persistence writes:
        None besides retriever-side RPCs owned by Hybrid/graph/table.

    External/model calls:
        Direct Hybrid, GraphRetriever with precomputed keywords, table
        executor, and citation ID lookup. No catalog LLM. Empty graph
        keywords fail rather than extract.

    Budget/deadline behavior:
        Every branch inherits run_id, reservation, deadline, and
        cancellation. Concurrency is capped at 2.

    Failure/fallback route:
        Graph unavailability degrades Combined to Hybrid. Historical
        graph paths fail closed. Hybrid/table never fall back to graph
        prose.

    Args:
        state: State after planning.
        deps: Optional retrievers.

    Returns:
        State with branch result mappings.
    """

    if skip_closed_nodes(state) or state.get("retrieval_plan") is None:
        return state
    context = runtime_from_state(state)
    prep_raw = state.get("preparation")
    plan_raw = state.get("retrieval_plan")
    if context is None or prep_raw is None or plan_raw is None:
        return state
    try:
        prep = preparation_from_state(prep_raw)
        plan = plan_from_state(plan_raw)
    except ValueError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": str(exc) or "invalid_plan",
        }
    query_budget = retrieve_budget(state, context)
    try:
        results = execute_branches(
            plan,
            prep,
            context,
            hybrid_retriever=deps.hybrid_retriever,
            graph_retriever=deps.graph_retriever,
            table_executor=deps.table_executor,
            query_budget=query_budget,
            cancel_check=deps.cancel_check,
        )
    except QueryRoutingError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": exc.reason,
            "keyword_extract_count": 0,
            "catalog_llm_call_count": 0,
        }
    extract_total = sum(item.keyword_extract_count for item in results)
    authorized = runtime_after_retrieve_budget(context, query_budget)
    return {
        **state,
        "status": "branches_executed",
        "authorized_runtime": authorized.model_dump(mode="json"),
        "branch_results": [item.model_dump(mode="json") for item in results],
        "keyword_extract_count": extract_total,
        "catalog_llm_call_count": 0,
        "remaining_model_calls": query_budget.remaining_model_calls,
        "detail": "branches executed; fusion and answering are not implemented",
    }


execute_branches_node = company_scope_node
