"""Attach the retrieve-time remaining ledger onto Hybrid and graph adapters."""

from __future__ import annotations

from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_routing.protocols import GraphRetrieveLike, HybridRetrieveLike
from smart_rag_core.security.identity import CallerContext


def attach_retrieve_budget(
    *,
    runtime: AuthorizedRuntimeContext,
    caller: CallerContext,
    hybrid_retriever: HybridRetrieveLike | None,
    graph_retriever: GraphRetrieveLike | None,
    query_budget: QueryRetrieveBudget | None,
) -> QueryRetrieveBudget:
    """Bind the retrieve-time remaining ledger onto Hybrid and graph adapters.

    Args:
        runtime: Packet 1 context. Used when ``query_budget`` is omitted.
        caller: Server-derived caller copied onto a newly created ledger.
        hybrid_retriever: Optional Hybrid adapter.
        graph_retriever: Optional graph adapter.
        query_budget: Remaining after earlier counted calls. ``None`` starts
            at ``runtime.model_call_ceiling`` (standalone branch tests).

    Returns:
        The ledger bound onto adapters. Retrieve mutates it in place.
    """

    retrieve_budget = query_budget or QueryRetrieveBudget(
        remaining_model_calls=runtime.model_call_ceiling,
        remaining_usd=runtime.remaining_usd,
        caller=caller,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        expected_version=runtime.optimistic_version,
    )
    if retrieve_budget.caller is None:
        retrieve_budget.caller = caller
    if retrieve_budget.run_id is None:
        retrieve_budget.run_id = runtime.run_id
    if retrieve_budget.reservation_id is None:
        retrieve_budget.reservation_id = runtime.reservation_id
    if hybrid_retriever is not None:
        supabase = getattr(hybrid_retriever, "_supabase", None)
        if supabase is not None:
            retrieve_budget.connection = supabase
        hybrid_retriever.query_budget = retrieve_budget
    if graph_retriever is not None:
        graph_retriever.query_budget = retrieve_budget
    return retrieve_budget
