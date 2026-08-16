"""Query graph nodes for packet 2. Admission stays first; no answer node."""

from __future__ import annotations

from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.constants import FALLBACK_MEMORY_UNAVAILABLE
from smart_rag_core.query_routing.correction import (
    apply_correction_to_plan,
    decide_correction,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.memory import load_authorized_memory
from smart_rag_core.query_routing.models import BranchResult, RoutingSurface
from smart_rag_core.query_routing.preparation import caller_from_runtime, prepare_query
from smart_rag_core.query_routing.serde import (
    branch_results_from_state,
    memory_from_state,
    plan_from_state,
    preparation_from_state,
)

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.state import QueryGraphState


def _runtime(state: QueryGraphState) -> AuthorizedRuntimeContext | None:
    """Parse authorized runtime from graph state.

    Args:
        state: Query graph state.

    Returns:
        Frozen context, or None when missing/invalid.
    """

    raw = state.get("authorized_runtime")
    try:
        return AuthorizedRuntimeContext.from_mapping(raw)
    except (ValueError, TypeError):
        return None


def _skip_if_closed(state: QueryGraphState) -> bool:
    """Return whether later nodes must pass through without work.

    Args:
        state: Query graph state.

    Returns:
        True when admission or routing already failed closed.
    """

    return state["status"] in {"admission_rejected", "routing_rejected"}


def load_memory_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Load bounded creator-only messages as untrusted delimited records.

    State inputs:
        ``authorized_runtime``, ``status`` after ``enforce_admission``.

    State outputs:
        ``memory_records`` (possibly empty) and ``status=memory_loaded``.

    Persistence writes:
        None. Reads ``app.load_query_memory`` only.

    External/model calls:
        None.

    Budget/deadline behavior:
        No reservation consume. Deleted/foreign conversations fail closed.

    Failure/fallback route:
        Without a connection, records empty memory and
        ``memory_unavailable``. Deleted conversation sets
        ``routing_rejected``. Never copies source documents.

    Args:
        state: Admitted query graph state.
        deps: Optional database binding.

    Returns:
        State with memory records.
    """

    if _skip_if_closed(state):
        return state
    context = _runtime(state)
    if context is None:
        return {**state, "status": "admission_rejected"}
    if deps.connection is None:
        return {
            **state,
            "status": "memory_loaded",
            "memory_records": [],
            "detail": FALLBACK_MEMORY_UNAVAILABLE,
        }
    try:
        records = load_authorized_memory(
            deps.connection,
            caller=caller_from_runtime(context),
            conversation_id=context.conversation_id,
        )
    except QueryRoutingError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": exc.reason,
            "memory_records": [],
        }
    dumped = [item.model_dump(mode="json") for item in records]
    return {
        **state,
        "status": "memory_loaded",
        "memory_records": dumped,
        "detail": "memory loaded as untrusted delimited records",
    }


def prepare_query_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Build one typed preparation with at most one counted model call.

    State inputs:
        ``user_query``, ``memory_records``, ``authorized_runtime``,
        ``routing_surface``, ``requested_manual_route``.

    State outputs:
        ``preparation`` mapping and decremented ``remaining_model_calls``
        when the one prep call ran.

    Persistence writes:
        Counted ``profile`` usage when a model call is consumed.

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

    if _skip_if_closed(state):
        return state
    context = _runtime(state)
    if context is None:
        return {**state, "status": "admission_rejected"}
    surface_raw = state.get("routing_surface") or RoutingSurface.PRODUCTION.value
    try:
        surface = RoutingSurface(str(surface_raw))
    except ValueError:
        surface = RoutingSurface.PRODUCTION
    memory = memory_from_state(state.get("memory_records"))
    remaining_calls = state["remaining_model_calls"]
    try:
        preparation = prepare_query(
            str(state.get("user_query") or ""),
            runtime=context,
            memory=memory,
            routing_surface=surface,
            requested_manual_route=state.get("requested_manual_route"),
            model_caller=deps.model_caller,
            force_model=deps.force_model,
            connection=deps.connection,
            caller=caller_from_runtime(context),
        )
    except QueryRoutingError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": exc.reason,
        }
    if preparation.model_calls == 1:
        try:
            remaining_calls = assert_call_available(remaining_calls)
        except QueryCeilingError:
            remaining_calls = 0
    return {
        **state,
        "status": "prepared",
        "preparation": preparation.model_dump(mode="json"),
        "remaining_model_calls": remaining_calls,
        "keyword_extract_count": 0,
        "catalog_llm_call_count": 0,
        "detail": "query prepared; answering is not implemented",
    }


def compile_plan_node(state: QueryGraphState) -> QueryGraphState:
    """Compile the deterministic route/limitation matrix.

    State inputs:
        ``preparation``, ``authorized_runtime``, ``requested_manual_route``.

    State outputs:
        ``retrieval_plan``, ``requested_route``, ``effective_route``.

    Persistence writes:
        None. Packet 7 owns durable checkpoints.

    External/model calls:
        None. Catalog-search LLMs are forbidden.

    Budget/deadline behavior:
        Effective family is clamped to the reserved envelope.

    Failure/fallback route:
        Production manual override and fourth subquestion reject the run.

    Args:
        state: State after preparation.

    Returns:
        State with a frozen retrieval plan mapping.
    """

    if _skip_if_closed(state) or state.get("preparation") is None:
        return state
    context = _runtime(state)
    if context is None:
        return {**state, "status": "admission_rejected"}
    try:
        prep = preparation_from_state(state["preparation"])
    except ValueError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": str(exc) or "invalid_preparation",
        }
    try:
        plan = compile_retrieval_plan(
            prep,
            context,
            requested_manual_route=state.get("requested_manual_route"),
        )
    except QueryRoutingError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": exc.reason,
        }
    return {
        **state,
        "status": "planned",
        "retrieval_plan": plan.model_dump(mode="json"),
        "requested_route": plan.requested_route.value,
        "effective_route": plan.effective_route.value,
        "corrected_route": None,
        "catalog_llm_call_count": 0,
        "detail": "retrieval plan compiled; answering is not implemented",
    }


def execute_branches_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Run bounded parallel retrieval branches without fusion or answering.

    State inputs:
        ``retrieval_plan``, ``preparation``, ``authorized_runtime``.

    State outputs:
        ``branch_results`` and keyword/catalog counters (must stay 0).

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

    if _skip_if_closed(state) or state.get("retrieval_plan") is None:
        return state
    context = _runtime(state)
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
    try:
        results = execute_branches(
            plan,
            prep,
            context,
            hybrid_retriever=deps.hybrid_retriever,
            graph_retriever=deps.graph_retriever,
            table_executor=deps.table_executor,
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
    return {
        **state,
        "status": "branches_executed",
        "branch_results": [item.model_dump(mode="json") for item in results],
        "keyword_extract_count": extract_total,
        "catalog_llm_call_count": 0,
        "detail": "branches executed; fusion and answering are not implemented",
    }


def apply_correction_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Apply at most one global correction, then end without answering.

    State inputs:
        plan, preparation, branch results, remaining_corrections,
        correction_applied.

    State outputs:
        ``correction``, possibly extra branch results, ``corrected_route``,
        and ``insufficient_evidence`` when exhausted.

    Persistence writes:
        None. ``routing_correction`` is stored on graph state for packet 3.

    External/model calls:
        At most one extra Combined or same-route retrieve. Never both.
        Never a correction loop.

    Budget/deadline behavior:
        Consumes the single remaining correction slot. Combined escalation
        is skipped when the reserved envelope cannot enlarge.

    Failure/fallback route:
        Exhaustion is verified partial/insufficient evidence, not an answer.
        Historical relationships cannot take a graph path.

    Args:
        state: State after branch execution.
        deps: Retrievers for the optional extra branch.

    Returns:
        Terminal packet-2 state. No answer node follows.
    """

    if _skip_if_closed(state):
        return state
    if state.get("retrieval_plan") is None or state.get("preparation") is None:
        return state
    context = _runtime(state)
    if context is None:
        return state
    try:
        prep = preparation_from_state(state["preparation"])
        plan = plan_from_state(state["retrieval_plan"])
        results = branch_results_from_state(state.get("branch_results"))
    except ValueError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": str(exc) or "invalid_correction_state",
        }
    already = bool(state.get("correction_applied"))
    try:
        decision = decide_correction(
            plan,
            prep,
            results,
            runtime=context,
            remaining_corrections=state["remaining_corrections"],
            already_applied=already,
        )
    except QueryRoutingError as exc:
        return {
            **state,
            "status": "routing_rejected",
            "detail": exc.reason,
        }
    extra: list[BranchResult] = []
    updated = plan
    if decision.applied:
        updated = apply_correction_to_plan(plan, prep, decision, results)
        new_specs = updated.branches[len(plan.branches) :]
        if new_specs:
            extra_plan = updated.model_copy(update={"branches": new_specs})
            try:
                extra = list(
                    execute_branches(
                        extra_plan,
                        prep,
                        context,
                        hybrid_retriever=deps.hybrid_retriever,
                        graph_retriever=deps.graph_retriever,
                        table_executor=deps.table_executor,
                        cancel_check=deps.cancel_check,
                    )
                )
            except QueryRoutingError as exc:
                return {
                    **state,
                    "status": "insufficient_evidence",
                    "detail": exc.reason,
                    "correction": decision.model_dump(mode="json"),
                    "remaining_corrections": decision.remaining_corrections,
                    "correction_applied": True,
                }
    combined = (*results, *extra)
    terminal = "correction_applied"
    detail = "one correction applied; answering is not implemented"
    if not decision.applied:
        detail = "no correction; answering is not implemented"
    if decision.exhausted_status == "insufficient_evidence":
        terminal = "insufficient_evidence"
        detail = "insufficient evidence; answering is not implemented"
    whole_refused = any(
        item.fallback_reason == "section_coverage_below_1" for item in combined
    )
    if whole_refused:
        terminal = "insufficient_evidence"
        detail = "section_coverage_ratio below 1.0; scoped refusal"
    return {
        **state,
        "status": terminal,
        "detail": detail,
        "retrieval_plan": updated.model_dump(mode="json"),
        "branch_results": [item.model_dump(mode="json") for item in combined],
        "correction": decision.model_dump(mode="json"),
        "corrected_route": updated.corrected_route.value
        if updated.corrected_route is not None
        else None,
        "effective_route": updated.effective_route.value,
        "remaining_corrections": decision.remaining_corrections,
        "correction_applied": decision.applied or already,
        "keyword_extract_count": sum(item.keyword_extract_count for item in combined),
        "catalog_llm_call_count": 0,
    }
