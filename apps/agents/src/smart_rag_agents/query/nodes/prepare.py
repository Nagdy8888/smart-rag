"""Prepare one typed query profile with at most one counted model call."""

from __future__ import annotations

from typing import cast

from smart_rag_core.query_admission.ceilings import (
    ANSWER_STAGE_RESERVED_MODEL_CALLS,
    assert_call_available,
)
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import RoutingSurface
from smart_rag_core.query_routing.preparation import caller_from_runtime, prepare_query
from smart_rag_core.query_routing.serde import memory_from_state

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import (
    runtime_after_consume,
    runtime_from_state,
    skip_closed_nodes,
)
from smart_rag_agents.query.nodes.tokens import accumulated_tokens, tokens_from_caller
from smart_rag_agents.query.state import QueryGraphState


def prepare_query_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Build one typed preparation with at most one counted model call.

    State inputs:
        ``user_query``, ``memory_records``, ``authorized_runtime``,
        ``routing_surface``, ``requested_manual_route``. Requested search
        scope is read from the authorized runtime, never from untrusted
        graph fields.

    State outputs:
        ``preparation`` mapping, decremented ``remaining_model_calls``
        when the one prep call ran, accumulated ``prompt_tokens`` /
        ``completion_tokens`` from that call, and ``authorized_runtime``
        with the post-profile reservation version.

    Persistence writes:
        Counted ``profile`` usage when a model call is consumed. The usage
        row records ``deps.profile_model_id``.

    External/model calls:
        Zero or one structured rewrite-plus-profile call. Never a separate
        rewrite call and never LightRAG keyword extract.

    Budget/deadline behavior:
        Uses ``execute_counted_model_call`` against the run-local reservation.
        Does not enlarge packet 1 ceilings.

    Failure/fallback route:
        Empty query, production manual override, or original-query loss
        sets ``routing_rejected``. Deterministic profiles skip the model.

    Args:
        state: State after memory load.
        deps: Optional model caller and connection.

    Returns:
        State with ``QueryPreparation`` dumped to a mapping.
    """

    if skip_closed_nodes(state):
        return state
    context = runtime_from_state(state)
    if context is None:
        return {**state, "status": "admission_rejected"}
    surface_raw = state.get("routing_surface") or RoutingSurface.PRODUCTION.value
    try:
        surface = RoutingSurface(str(surface_raw))
    except ValueError:
        surface = RoutingSurface.PRODUCTION
    memory = memory_from_state(state.get("memory_records"))
    remaining_calls = state["remaining_model_calls"]
    consumed: list[ReservationConsumeResult] = []
    model_caller = deps.model_caller
    force_model = deps.force_model
    if remaining_calls < ANSWER_STAGE_RESERVED_MODEL_CALLS + 1:
        model_caller = None
        force_model = False
    try:
        preparation = prepare_query(
            str(state.get("user_query") or ""),
            runtime=context,
            memory=memory,
            routing_surface=surface,
            requested_manual_route=state.get("requested_manual_route"),
            requested_search_scope=context.requested_search_scope,
            model_caller=model_caller,
            force_model=force_model,
            connection=deps.connection,
            caller=caller_from_runtime(context),
            model_id=deps.profile_model_id,
            on_reservation_consume=consumed.append,
        )
    except QueryRoutingError as exc:
        return cast(
            QueryGraphState,
            {
                **state,
                "status": "routing_rejected",
                "detail": exc.reason,
            },
        )
    if preparation.model_calls == 1:
        try:
            remaining_calls = assert_call_available(remaining_calls)
        except QueryCeilingError:
            remaining_calls = 0
    authorized = context
    if consumed:
        authorized = runtime_after_consume(context, consumed[0])
    added_prompt, added_completion = (0, 0)
    if preparation.model_calls == 1:
        added_prompt, added_completion = tokens_from_caller(deps.model_caller)
    return cast(
        QueryGraphState,
        {
            **state,
            "status": "prepared",
            "authorized_runtime": authorized.model_dump(mode="json"),
            "preparation": preparation.model_dump(mode="json"),
            "remaining_model_calls": remaining_calls,
            "keyword_extract_count": 0,
            "catalog_llm_call_count": 0,
            "knowledge_scope": preparation.knowledge_scope.value,
            "requested_search_scope": preparation.requested_search_scope.value,
            "no_retrieval_answer_mode": None,
            "scope_degradation_reason": (
                None
                if preparation.scope_degradation_reason is None
                else preparation.scope_degradation_reason.value
            ),
            "detail": "query prepared; answering is not implemented",
            **accumulated_tokens(state, added_prompt, added_completion),
        },
    )
