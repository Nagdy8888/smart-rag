"""Shared closed-state guards and retrieve-budget reconstruction."""

from __future__ import annotations

from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_routing.models import RetrievalPlan
from smart_rag_core.query_routing.preparation import caller_from_runtime

from smart_rag_agents.query.state import QueryGraphState


def runtime_after_consume(
    context: AuthorizedRuntimeContext, consumed: ReservationConsumeResult
) -> AuthorizedRuntimeContext:
    """Copy remaining holds after one durable reservation consume.

    Each consume increments ``optimistic_version``. The next counted
    call must use the new version or Postgres returns
    ``optimistic_version_conflict``.

    Args:
        context: Runtime snapshot before this consume.
        consumed: Durable consume outcome.

    Returns:
        Frozen runtime with the new version and remaining holds.
    """

    return context.model_copy(
        update={
            "optimistic_version": consumed.optimistic_version,
            "remaining_usd": consumed.remaining_usd,
            "remaining_prompt_tokens": consumed.remaining_prompt_tokens,
            "remaining_completion_tokens": consumed.remaining_completion_tokens,
        }
    )


def runtime_after_retrieve_budget(
    context: AuthorizedRuntimeContext, budget: QueryRetrieveBudget
) -> AuthorizedRuntimeContext:
    """Copy retrieve-ledger holds onto authorized runtime after branches.

    Args:
        context: Runtime snapshot used to start retrieve.
        budget: Ledger updated in place by counted retrieve consumes.

    Returns:
        Frozen runtime whose version and remaining USD match the ledger.
    """

    return context.model_copy(
        update={
            "optimistic_version": budget.expected_version,
            "remaining_usd": budget.remaining_usd,
        }
    )


def runtime_from_state(state: QueryGraphState) -> AuthorizedRuntimeContext | None:
    """Parse authorized runtime from graph state.

    Args:
        state: Query graph state.

    Returns:
        Frozen context, or None when missing or invalid.
    """

    raw = state.get("authorized_runtime")
    try:
        return AuthorizedRuntimeContext.from_mapping(raw)
    except (ValueError, TypeError):
        return None


def skip_closed_nodes(state: QueryGraphState) -> bool:
    """Return whether later nodes must pass through without work.

    Args:
        state: Query graph state.

    Returns:
        True when admission, routing, or exhausted retrieval already
        failed closed.
    """

    return state["status"] in {
        "admission_rejected",
        "routing_rejected",
        "insufficient_evidence",
    }


def retrieve_budget(
    state: QueryGraphState,
    context: AuthorizedRuntimeContext,
    *,
    connection: object | None = None,
) -> QueryRetrieveBudget:
    """Start retrieve remaining from graph state, not the original ceiling.

    Args:
        state: Graph state after profile or other prior counted calls.
        context: Frozen admit context.
        connection: Per-run ``app_api`` connection used for durable
            embedding, rerank, and verifier accounting. Missing on a
            counted retrieve with reservation ids fails closed.

    Returns:
        Mutable ledger whose remaining model calls the retrieve node
        writes back onto graph state.
    """

    return QueryRetrieveBudget(
        remaining_model_calls=int(state["remaining_model_calls"]),
        remaining_usd=context.remaining_usd,
        connection=connection,
        caller=caller_from_runtime(context),
        run_id=context.run_id,
        reservation_id=context.reservation_id,
        expected_version=context.optimistic_version,
    )


def route_needs_retrieval(plan: RetrievalPlan | None) -> bool:
    """Return whether the compiled plan requires Hybrid or table evidence.

    Args:
        plan: Compiled retrieval plan, or None when missing.

    Returns:
        False for NoRetrieval and graph-only inspection. True otherwise,
        including when the plan is missing (fail closed).
    """

    if plan is None:
        return True
    if plan.company_claim_forbidden or plan.graph_as_answer_forbidden:
        return False
    return True
