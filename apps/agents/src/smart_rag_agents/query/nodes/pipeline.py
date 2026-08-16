"""Query graph nodes for packets 2-4. Admission stays first."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from smart_rag_core.memory.payload import memory_store_namespace
from smart_rag_core.query_admission.ceilings import (
    assert_call_available,
    assert_deadline_open,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import generate_answer
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
    TableComposition,
    VerificationResult,
    VerifierPayload,
)
from smart_rag_core.query_answer.tables import compose_tables
from smart_rag_core.query_answer.verifier import run_verifier_batch
from smart_rag_core.query_answer.versions import (
    ANSWER_MODEL_ID,
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)
from smart_rag_core.query_fusion import SELECTED_FUSION_ALGORITHM, fuse_evidence
from smart_rag_core.query_fusion.assemble import fusion_input_from_branches
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.models import FusionResult
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
from smart_rag_core.query_routing.safety import delimit_memory_record
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


def runtime_from_state(state: QueryGraphState) -> AuthorizedRuntimeContext | None:
    """Parse authorized runtime from graph state for sibling node modules.

    Args:
        state: Query graph state.

    Returns:
        Frozen context, or None when missing/invalid.
    """

    return _runtime(state)


def skip_closed_nodes(state: QueryGraphState) -> bool:
    """Return whether later nodes must pass through without work.

    Args:
        state: Query graph state.

    Returns:
        True when admission or routing already failed closed.
    """

    return _skip_if_closed(state)


def load_memory_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Load bounded creator-only messages as untrusted delimited records.

    State inputs:
        ``authorized_runtime``, ``status`` after ``enforce_admission``.

    State outputs:
        ``memory_records`` (possibly empty) and ``status=memory_loaded``.

    Persistence writes:
        None. Reads ``app.load_query_memory`` and optional compact store
        summaries. Source documents are never joined.

    External/model calls:
        None.

    Budget/deadline behavior:
        No reservation consume. Deleted/foreign conversations fail closed.

    Failure/fallback route:
        Without a connection, records empty memory and
        ``memory_unavailable``. Deleted conversation sets
        ``routing_rejected``. Invalid store payloads are skipped.

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
    if deps.store_get is not None:
        namespace = memory_store_namespace(
            company_id=None,
            user_id=str(context.user_id),
            conversation_id=str(context.conversation_id),
        )
        stored = deps.store_get(namespace, "summary")
        summary_text = stored.get("summary") if stored else None
        if isinstance(summary_text, str) and summary_text:
            summary_record = delimit_memory_record(
                message_id=str(
                    uuid5(NAMESPACE_URL, f"summary:{context.conversation_id}")
                ),
                role="system",
                content=summary_text,
                created_at="1970-01-01T00:00:00+00:00",
            )
            dumped = [summary_record.model_dump(mode="json"), *dumped]
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
        State after the single correction. Packet 3 nodes follow.
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
    detail = "one correction applied; fusion and answering follow"
    if not decision.applied:
        detail = "no correction; fusion and answering follow"
    if decision.exhausted_status == "insufficient_evidence":
        terminal = "insufficient_evidence"
        detail = "insufficient evidence; verified partial follows"
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


def fuse_evidence_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Fuse Hybrid ranks with resolved graph paths. Never graph-only answers.

    State inputs:
        ``branch_results``, ``requested_route``, ``effective_route``,
        ``keyword_extract_count``.

    State outputs:
        ``fusion``, ``selected_algorithm``, ``fusion_config_hash``,
        possibly ``effective_route=hybrid`` with a typed graph reason.

    Persistence writes:
        None. Scores are stored on graph state for citation provenance.

    External/model calls:
        None. Fusion weights are frozen constants.

    Budget/deadline behavior:
        Deadline exhaustion yields verified partial without fabricating
        relationship evidence.

    Failure/fallback route:
        Unusable graph (timeout, survival < 0.50, outage) keeps
        ``requested_route`` and sets ``effective_route=hybrid``. Hidden
        LightRAG keyword/answer counters fail closed.

    Args:
        state: State after the single correction.
        deps: Unused; fusion is pure. Present for node signature symmetry.

    Returns:
        State with a ``FusionResult`` mapping.
    """

    del deps
    if _skip_if_closed(state):
        return state
    if state["status"] in {"refused"}:
        return state
    try:
        results = branch_results_from_state(state.get("branch_results"))
        fusion_input = fusion_input_from_branches(
            results,
            requested_route=str(state.get("requested_route") or "hybrid"),
            effective_route=str(state.get("effective_route") or "hybrid"),
        )
        fusion = fuse_evidence(fusion_input, algorithm=SELECTED_FUSION_ALGORITHM)
    except (FusionError, QueryRoutingError, ValueError) as exc:
        reason = getattr(exc, "reason", str(exc) or "fusion_failed")
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": str(reason),
            "fusion": None,
        }
    return {
        **state,
        "status": "fused",
        "detail": "canonical evidence fused",
        "fusion": fusion.model_dump(mode="json"),
        "effective_route": fusion.effective_route,
        "requested_route": fusion.requested_route,
        "selected_algorithm": fusion.algorithm.value,
        "fusion_config_hash": fusion.config_hash,
        "keyword_extract_count": 0,
        "catalog_llm_call_count": 0,
    }


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
    if _skip_if_closed(state):
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


def generate_answer_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Generate exactly one answer from canonical passages and table values.

    State inputs:
        ``fusion``, ``table_composition``, ``user_query``, ``retrieval_plan``,
        ``remaining_model_calls``.

    State outputs:
        ``answer`` and decremented ``remaining_model_calls`` when a counted
        ``usage_kind=answer`` call ran.

    Persistence writes:
        Counted ``answer`` usage when a connection and gateway are bound.

    External/model calls:
        Zero or one answer generation. Never a second. LightRAG
        ``answer_generate`` stays 0.

    Budget/deadline behavior:
        Uses ``execute_counted_model_call`` against the run-local reservation
        when a live adapter runs. Deadline exhaustion is verified partial.

    Failure/fallback route:
        Empty evidence, NoRetrieval, and graph inspection refuse without a
        fake success. Unbound adapters use the extractive mock.

    Args:
        state: State after table composition.
        deps: Optional gateway, prompt text, and connection.

    Returns:
        State with an ``AnswerPayload`` mapping.
    """

    if _skip_if_closed(state):
        return state
    context = _runtime(state)
    fusion = _fusion_from_state(state.get("fusion"))
    tables = _tables_from_state(state.get("table_composition"))
    plan = None
    if state.get("retrieval_plan") is not None:
        try:
            plan = plan_from_state(state["retrieval_plan"])
        except ValueError:
            plan = None
    company_forbidden = plan.company_claim_forbidden if plan is not None else False
    graph_forbidden = plan.graph_as_answer_forbidden if plan is not None else False
    remaining = state["remaining_model_calls"]
    answer_calls = state.get("answer_call_count") or 0
    needs_model = bool(fusion.evidence or tables.records) and not (
        company_forbidden or graph_forbidden
    )
    if needs_model:
        try:
            remaining = assert_call_available(remaining)
        except QueryCeilingError:
            return {
                **state,
                "status": "verified_partial",
                "detail": "model_call_exhausted",
                "answer": AnswerPayload(
                    answer_text="Verified partial: model-call ceiling exhausted.",
                    status="partial",
                ).model_dump(mode="json"),
            }
        if context is not None:
            try:
                assert_deadline_open(
                    now=datetime.now(UTC), deadline_at=context.deadline_at
                )
            except QueryCeilingError:
                return {
                    **state,
                    "status": "verified_partial",
                    "detail": "deadline_exhausted",
                    "answer": AnswerPayload(
                        answer_text="Verified partial: deadline exhausted.",
                        status="partial",
                    ).model_dump(mode="json"),
                }
    caller = None
    if needs_model and deps.model_gateway is not None and deps.answer_prompt_text:

        def _send() -> AnswerPayload:
            """Invoke the shared gateway answer operation.

            Returns:
                Parsed answer payload.
            """

            return _gateway_answer(
                deps,
                query=str(state.get("user_query") or ""),
                fusion=fusion,
                tables=tables.records,
                remaining=remaining,
            )

        if deps.connection is not None and context is not None:
            payload, _consumed, _usage_id = execute_counted_model_call(
                deps.connection,
                caller=caller_from_runtime(context),
                run_id=context.run_id,
                reservation_id=context.reservation_id,
                expected_version=context.optimistic_version,
                usage_kind="answer",
                model_id=ANSWER_MODEL_ID,
                provider_attempt_id=str(uuid4()),
                send=_send,
            )
            answer = payload
        else:
            answer = _send()
        answer_calls = 1
    else:
        try:
            answer = generate_answer(
                fusion=fusion,
                tables=tables.records,
                user_query=str(state.get("user_query") or "query"),
                caller=caller,
                already_generated=answer_calls,
                company_claim_forbidden=company_forbidden,
                graph_as_answer_forbidden=graph_forbidden,
            )
        except AnswerError as exc:
            return {
                **state,
                "status": "insufficient_evidence",
                "detail": exc.reason,
            }
        if needs_model:
            answer_calls = 1
    status = "answered"
    if answer.status == "refused" and not fusion.evidence and not tables.records:
        status = "insufficient_evidence"
    return {
        **state,
        "status": status,
        "detail": "one answer generated from canonical evidence",
        "answer": answer.model_dump(mode="json"),
        "remaining_model_calls": remaining,
        "answer_call_count": answer_calls,
        "catalog_llm_call_count": int(state.get("catalog_llm_call_count") or 0),
        "keyword_extract_count": 0,
    }


def verify_answer_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Deterministic citation checks, then at most one six-link verifier call.

    State inputs:
        ``answer``, ``fusion``, ``table_composition``,
        ``remaining_model_calls``, ``verifier_call_count``.

    State outputs:
        ``verification`` and possibly decremented remaining calls.

    Persistence writes:
        Counted ``verifier`` usage when a connection and gateway are bound.
        Citation provenance may be inserted when a connection is bound.

    External/model calls:
        Zero or one small verifier call covering at most six material
        links. A seventh link is omitted. Never a second verifier call.

    Budget/deadline behavior:
        Deadline/step exhaustion emits verified partial, not fake success.

    Failure/fallback route:
        Unsupported links are removed or refused. Unsupported chains drop
        the composed conclusion. Inspection/NoRetrieval stay refused.

    Args:
        state: State after answer generation.
        deps: Optional gateway and connection.

    Returns:
        Terminal verified state.
    """

    if _skip_if_closed(state):
        return state
    fusion = _fusion_from_state(state.get("fusion"))
    tables = _tables_from_state(state.get("table_composition"))
    raw_answer = state.get("answer")
    if raw_answer is None:
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": "missing_answer",
        }
    payload = AnswerPayload.model_validate(raw_answer)
    checked, failures = deterministic_check_answer(
        payload, fusion=fusion, tables=tables.records
    )
    remaining = state["remaining_model_calls"]
    verifier_calls = state.get("verifier_call_count") or 0
    omitted: tuple[str, ...] = ()
    if checked.atomic_links:
        caller = None
        if deps.model_gateway is not None and deps.verifier_prompt_text:

            def _verifier_caller(links: tuple[AtomicLink, ...]) -> VerifierPayload:
                """Invoke one verifier batch through the bound gateway.

                Args:
                    links: At most six material links.

                Returns:
                    Structured verifier payload.
                """

                return _gateway_verifier(
                    deps,
                    links=links,
                    fusion=fusion,
                    tables=tables.records,
                    remaining=remaining,
                )

            caller = _verifier_caller
        try:
            if caller is not None:
                remaining = assert_call_available(remaining)
            checked, verifier_calls, omitted = run_verifier_batch(
                checked,
                caller=caller,
                already_called=verifier_calls,
            )
        except (AnswerError, QueryCeilingError) as exc:
            reason = getattr(exc, "reason", str(exc) or "verifier_failed")
            if str(reason) == "model_call_exhausted":
                return {
                    **state,
                    "status": "verified_partial",
                    "detail": "model_call_exhausted",
                    "answer": checked.model_dump(mode="json"),
                }
            return {
                **state,
                "status": "verified_partial",
                "detail": str(reason),
                "answer": checked.model_dump(mode="json"),
            }
    terminal = "verified_partial"
    if checked.status == "refused" and not fusion.evidence and not tables.records:
        terminal = "insufficient_evidence"
        detail = "insufficient authorized evidence"
    elif checked.status == "refused":
        terminal = "refused"
        detail = "answer refused after verification"
    elif checked.status == "partial" or failures or omitted:
        terminal = "verified_partial"
        detail = "verified partial after citation checks"
    else:
        terminal = "verified"
        detail = "answer verified"
    result = VerificationResult(
        answer=checked,
        deterministic_failures=failures,
        verifier_call_count=1 if verifier_calls else 0,
        omitted_link_ids=omitted,
        status=terminal
        if terminal
        in {"verified", "verified_partial", "refused", "insufficient_evidence"}
        else "verified_partial",
    )
    return {
        **state,
        "status": terminal,
        "detail": detail,
        "answer": checked.model_dump(mode="json"),
        "verification": result.model_dump(mode="json"),
        "remaining_model_calls": remaining,
        "verifier_call_count": verifier_calls,
        "catalog_llm_call_count": int(state.get("catalog_llm_call_count") or 0),
        "keyword_extract_count": 0,
    }


def _fusion_from_state(raw: object) -> FusionResult:
    """Rebuild fusion output from graph state.

    Args:
        raw: Mapping or None.

    Returns:
        Fusion result. Empty Hybrid-effective result when missing.
    """

    if raw is None:
        return FusionResult(
            algorithm=SELECTED_FUSION_ALGORITHM,
            config_hash="0" * 64,
            requested_route="hybrid",
            effective_route="hybrid",
            evidence=(),
            graph_discovered_only_ratio=0.0,
        )
    return FusionResult.model_validate(raw)


def _tables_from_state(raw: object) -> TableComposition:
    """Rebuild table composition from graph state.

    Args:
        raw: Mapping or None.

    Returns:
        Table composition, empty when missing.
    """

    if raw is None:
        return TableComposition()
    return TableComposition.model_validate(raw)


def _gateway_answer(
    deps: QueryGraphDeps,
    *,
    query: str,
    fusion: FusionResult,
    tables: tuple[object, ...],
    remaining: int,
) -> AnswerPayload:
    """Run one async gateway answer call from the sync graph.

    Args:
        deps: Bound gateway and prompt.
        query: User query.
        fusion: Canonical evidence.
        tables: Table records.
        remaining: Remaining model calls, unused except as a timeout proxy.

    Returns:
        Parsed answer payload.

    Raises:
        AnswerError: If the gateway is unbound.
    """

    from typing import Any, cast

    from smart_rag_core.gateways.model import AnswerModelRequest
    from smart_rag_core.query_answer.assembly import assemble_source_records
    from smart_rag_core.query_answer.generate import filter_invented_ids
    from smart_rag_core.query_routing.models import TableEvidenceRecord

    typed_tables = tuple(
        item
        if isinstance(item, TableEvidenceRecord)
        else TableEvidenceRecord.model_validate(item)
        for item in tables
    )
    records = assemble_source_records(fusion, typed_tables)
    request = AnswerModelRequest(
        query=query or "query",
        prompt_version=ANSWER_PROMPT_VERSION,
        prompt_sha256=ANSWER_PROMPT_SHA256,
        prompt_text=str(deps.answer_prompt_text or "answer"),
        source_records=records or " ",
        chunk_ids=tuple(item.chunk_id for item in fusion.evidence),
        table_ids=tuple(item.table_id for item in typed_tables),
        remaining_deadline_seconds=max(0.1, min(45.0, float(remaining or 1))),
    )
    gateway = deps.model_gateway
    if gateway is None:
        raise AnswerError("model_gateway_unbound")
    response = cast(Any, _run_coro(cast(Any, gateway).generate_answer(request)))
    payload = AnswerPayload.model_validate(response.payload)
    return filter_invented_ids(payload, fusion, typed_tables)


def _gateway_verifier(
    deps: QueryGraphDeps,
    *,
    links: tuple[AtomicLink, ...],
    fusion: FusionResult,
    tables: tuple[object, ...],
    remaining: int,
) -> VerifierPayload:
    """Run one async gateway verifier call from the sync graph.

    Args:
        deps: Bound gateway and prompt.
        links: At most six atomic links.
        fusion: Canonical evidence.
        tables: Table records.
        remaining: Remaining model calls, unused except as a timeout proxy.

    Returns:
        ``VerifierPayload``.

    Raises:
        AnswerError: If the gateway is unbound.
    """

    from typing import Any, cast

    from smart_rag_core.gateways.model import VerifierModelRequest
    from smart_rag_core.query_answer.assembly import assemble_source_records
    from smart_rag_core.query_answer.models import VerifierPayload
    from smart_rag_core.query_routing.models import TableEvidenceRecord

    typed_tables = tuple(
        item
        if isinstance(item, TableEvidenceRecord)
        else TableEvidenceRecord.model_validate(item)
        for item in tables
    )
    records = assemble_source_records(fusion, typed_tables)
    request = VerifierModelRequest(
        prompt_version=VERIFIER_PROMPT_VERSION,
        prompt_sha256=VERIFIER_PROMPT_SHA256,
        prompt_text=str(deps.verifier_prompt_text or "verifier"),
        source_records=records or " ",
        links=tuple(
            cast(dict[str, object], item.model_dump(mode="json")) for item in links
        ),
        remaining_deadline_seconds=max(0.1, min(45.0, float(remaining or 1))),
    )
    gateway = deps.model_gateway
    if gateway is None:
        raise AnswerError("model_gateway_unbound")
    response = cast(Any, _run_coro(cast(Any, gateway).generate_verifier(request)))
    return VerifierPayload.model_validate(response.payload)


def _run_coro(coro: object) -> object:
    """Run one async gateway call from the sync query graph.

    Args:
        coro: Awaitable from ``ModelGateway``.

    Returns:
        Result.
    """

    import asyncio

    if asyncio.iscoroutine(coro):
        return asyncio.run(coro)
    return coro
