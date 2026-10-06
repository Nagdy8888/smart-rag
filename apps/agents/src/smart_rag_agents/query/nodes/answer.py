"""Generate exactly one answer from canonical passages or general chat."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

from smart_rag_core.query_admission.ceilings import (
    ANSWER_STAGE_MIN_SECONDS,
    assert_call_available,
    assert_deadline_open,
)
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.assembly import (
    company_deadline_reserve_payload,
    company_input_bound_payload,
    fit_source_records,
)
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import (
    apply_degraded_scope_framing,
    generate_answer,
)
from smart_rag_core.query_answer.locate import LocatedQuote
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.versions import ANSWER_MODEL_ID
from smart_rag_core.query_routing.constants import FALLBACK_RETRIEVERS_UNBOUND
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    NoRetrievalAnswerMode,
)
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.query_routing.serde import plan_from_state

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.answer import gateway_answer
from smart_rag_agents.query.gateway.general_chat import gateway_general_chat
from smart_rag_agents.query.nodes.answer_locate import run_locate_step
from smart_rag_agents.query.nodes.shared import (
    route_needs_retrieval,
    runtime_after_consume,
    runtime_from_state,
    skip_closed_nodes,
)
from smart_rag_agents.query.nodes.state_codec import (
    fusion_from_state,
    memory_text_from_state,
    tables_from_state,
)
from smart_rag_agents.query.nodes.tokens import accumulated_tokens
from smart_rag_agents.query.state import QueryGraphState


def generate_answer_node(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Generate exactly one answer from canonical passages and table values.

    State inputs:
        ``fusion``, ``table_composition``, ``user_query``, ``retrieval_plan``,
        ``remaining_model_calls``.

    State outputs:
        ``answer``, ``answer_locate`` (ID-only locate diagnostics), accumulated
        ``prompt_tokens`` / ``completion_tokens``, decremented
        ``remaining_model_calls`` when a counted ``usage_kind=answer`` call
        ran, and ``authorized_runtime`` with the post-answer reservation
        version.

    Persistence writes:
        Counted ``answer`` usage for the answer call and, when it runs, the
        locate call.

    External/model calls:
        Zero or one ``locate_v1`` call, then zero or one answer generation.
        Never a second answer generation. LightRAG ``answer_generate`` stays 0.

    Budget/deadline behavior:
        Uses ``execute_counted_model_call`` against the run-local reservation
        when a live adapter runs. Deadline exhaustion is verified partial.
        The locate call runs only with at least ``LOCATE_CALL_RESERVE`` calls
        and ``LOCATE_MIN_SECONDS`` remaining, and its timeout is
        ``LOCATE_TIMEOUT_SECONDS``.

    Failure/fallback route:
        Empty evidence, NoRetrieval, and graph inspection refuse without a
        fake success. Missing ``model_gateway`` or unbound Hybrid when the
        route needs retrieval never terminates ``verified``. A failed or
        skipped locate call never blocks the answer call; a refused answer
        with validated quotes is released as cited quotes with status
        ``partial``.

    Args:
        state: State after table composition.
        deps: Optional gateway, prompt text, Hybrid retriever, and connection.

    Returns:
        State with an ``AnswerPayload`` mapping.
    """

    if skip_closed_nodes(state):
        return state
    context = runtime_from_state(state)
    fusion = fusion_from_state(state.get("fusion"))
    tables = tables_from_state(state.get("table_composition"))
    plan = None
    if state.get("retrieval_plan") is not None:
        try:
            plan = plan_from_state(state["retrieval_plan"])
        except ValueError:
            plan = None
    company_forbidden = plan.company_claim_forbidden if plan is not None else False
    graph_forbidden = plan.graph_as_answer_forbidden if plan is not None else False
    knowledge_scope = plan.knowledge_scope if plan is not None else None
    answer_mode = plan.no_retrieval_answer_mode if plan is not None else None
    degradation = plan.scope_degradation_reason if plan is not None else None
    if answer_mode is NoRetrievalAnswerMode.DETERMINISTIC_CHAT:
        answer_mode = NoRetrievalAnswerMode.GENERAL_MODEL
    if route_needs_retrieval(plan) and deps.hybrid_retriever is None:
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": FALLBACK_RETRIEVERS_UNBOUND,
            "answer": AnswerPayload(
                answer_text="Insufficient authorized evidence.",
                status="refused",
                answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
            ).model_dump(mode="json"),
        }
    remaining = state["remaining_model_calls"]
    answer_calls = state.get("answer_call_count") or 0
    added_prompt_tokens = 0
    added_completion_tokens = 0
    runtime_update: dict[str, object] = {}
    fit_update: dict[str, object] = {}
    locate_update: dict[str, object] = {}
    locate_prompt_tokens = 0
    locate_completion_tokens = 0
    needs_rag_model = (
        bool(fusion.evidence or tables.records)
        and knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
        and not graph_forbidden
    )
    if knowledge_scope is None:
        needs_rag_model = bool(fusion.evidence or tables.records) and not (
            company_forbidden or graph_forbidden
        )
    needs_general_model = answer_mode in {
        NoRetrievalAnswerMode.GENERAL_MODEL,
        NoRetrievalAnswerMode.USER_TEXT_MODEL,
    }
    if needs_rag_model:
        needs_general_model = False
    working_fusion = fusion
    working_tables = tables.records
    if needs_rag_model:
        fit = fit_source_records(
            user_query=str(state.get("user_query") or ""),
            fusion=fusion,
            tables=tables.records,
            max_input_chars=deps.model_input_max_chars,
            route=fusion.effective_route,
        )
        fit_update["answer_context_fit"] = fit.diagnostics()
        fit_update["fusion"] = fit.fusion.model_dump(mode="json")
        working_fusion = fit.fusion
        working_tables = fit.tables
        if fit.trim_reason == "input_bound_exceeded":
            return cast(
                QueryGraphState,
                {
                    **state,
                    "status": "insufficient_evidence",
                    "detail": "input_bound_exceeded",
                    "answer": company_input_bound_payload().model_dump(mode="json"),
                    **fit_update,
                },
            )
        clock = deps.now if deps.now is not None else (lambda: datetime.now(UTC))
        if context is not None:
            remaining_seconds = (context.deadline_at - clock()).total_seconds()
            if remaining_seconds < ANSWER_STAGE_MIN_SECONDS:
                return cast(
                    QueryGraphState,
                    {
                        **state,
                        "status": "verified_partial",
                        "detail": "answer_deadline_reserve_exhausted",
                        "answer": company_deadline_reserve_payload().model_dump(
                            mode="json"
                        ),
                        **fit_update,
                    },
                )
    needs_model = needs_rag_model or needs_general_model
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
    prompt_ready = (
        bool(deps.answer_prompt_text)
        if needs_rag_model
        else bool(deps.general_chat_prompt_text)
    )
    if needs_model and (deps.model_gateway is None or not prompt_ready):
        return {
            **state,
            "status": "verified_partial",
            "detail": "model_gateway_unbound",
            "answer": AnswerPayload(
                answer_text="Verified partial: model gateway is unbound.",
                status="partial",
            ).model_dump(mode="json"),
        }
    if needs_model and deps.model_gateway is not None and prompt_ready:
        located: tuple[LocatedQuote, ...] = ()
        if needs_rag_model:
            outcome = run_locate_step(
                deps,
                query=str(state.get("user_query") or ""),
                fusion=working_fusion,
                tables=working_tables,
                context=context,
                remaining_model_calls=remaining,
            )
            located = outcome.quotes
            remaining = outcome.remaining_model_calls
            locate_prompt_tokens = outcome.prompt_tokens
            locate_completion_tokens = outcome.completion_tokens
            locate_update["answer_locate"] = outcome.diagnostics
            if outcome.context is not None and outcome.context is not context:
                runtime_update["authorized_runtime"] = outcome.context.model_dump(
                    mode="json"
                )
            context = outcome.context

        def _send() -> tuple[AnswerPayload, int, int]:
            """Invoke one RAG or general-chat gateway operation.

            Returns:
                Parsed answer payload plus provider token counts.
            """

            if needs_general_model:
                return gateway_general_chat(
                    deps,
                    query=str(state.get("user_query") or ""),
                    knowledge_scope=(
                        KnowledgeScope.USER_SUPPLIED_TEXT
                        if answer_mode is NoRetrievalAnswerMode.USER_TEXT_MODEL
                        else KnowledgeScope.GENERAL_KNOWLEDGE
                    ),
                    recent_memory=memory_text_from_state(state.get("memory_records")),
                    context=context,
                )
            return gateway_answer(
                deps,
                query=str(state.get("user_query") or ""),
                fusion=working_fusion,
                tables=working_tables,
                context=context,
                located=located,
            )

        def _usage_from_result(
            result: tuple[AnswerPayload, int, int],
        ) -> tuple[int | None, int | None, Decimal | None]:
            """Read provider tokens from a successful gateway send.

            Args:
                result: Payload plus prompt and completion counts.

            Returns:
                Prompt tokens, completion tokens, and no measured USD.
            """

            return result[1], result[2], None

        try:
            if deps.connection is not None and context is not None:
                counted, consumed, _usage_id = execute_counted_model_call(
                    deps.connection,
                    caller=caller_from_runtime(context),
                    run_id=context.run_id,
                    reservation_id=context.reservation_id,
                    expected_version=context.optimistic_version,
                    usage_kind="answer",
                    model_id=ANSWER_MODEL_ID,
                    provider_attempt_id=str(uuid4()),
                    send=_send,
                    usage_from_result=_usage_from_result,
                )
                answer, added_prompt_tokens, added_completion_tokens = counted
                runtime_update["authorized_runtime"] = runtime_after_consume(
                    context, consumed
                ).model_dump(mode="json")
            else:
                answer, added_prompt_tokens, added_completion_tokens = _send()
        except (AnswerError, QueryBudgetError, QueryCeilingError) as exc:
            reason = exc.reason
            if needs_rag_model:
                payload = company_input_bound_payload()
                status = "insufficient_evidence"
                if reason == "answer_deadline_reserve_exhausted":
                    payload = company_deadline_reserve_payload()
                    status = "verified_partial"
                elif reason != "input_bound_exceeded":
                    payload = AnswerPayload(
                        answer_text=(
                            "The available company evidence could not support "
                            "this answer."
                        ),
                        status="refused",
                        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
                    )
                return cast(
                    QueryGraphState,
                    {
                        **state,
                        "status": status,
                        "detail": reason,
                        "answer": payload.model_dump(mode="json"),
                        **fit_update,
                        **locate_update,
                    },
                )
            return {
                **state,
                "status": "verified_partial",
                "detail": reason,
                "answer": AnswerPayload(
                    answer_text="Verified partial: answer generation stopped.",
                    status="partial",
                ).model_dump(mode="json"),
            }
        answer = apply_degraded_scope_framing(
            answer, scope_degradation_reason=degradation
        )
        answer_calls = 1
    else:
        try:
            answer = generate_answer(
                fusion=working_fusion,
                tables=working_tables,
                user_query=str(state.get("user_query") or "query"),
                caller=caller,
                already_generated=answer_calls,
                company_claim_forbidden=company_forbidden,
                graph_as_answer_forbidden=graph_forbidden,
                knowledge_scope=knowledge_scope,
                no_retrieval_answer_mode=answer_mode,
                recent_memory=memory_text_from_state(state.get("memory_records")),
                scope_degradation_reason=degradation,
            )
        except AnswerError as exc:
            reason = exc.reason
            if needs_rag_model:
                payload = (
                    company_input_bound_payload()
                    if reason == "input_bound_exceeded"
                    else AnswerPayload(
                        answer_text=(
                            "The available company evidence could not support "
                            "this answer."
                        ),
                        status="refused",
                        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
                    )
                )
                return cast(
                    QueryGraphState,
                    {
                        **state,
                        "status": "insufficient_evidence",
                        "detail": reason,
                        "answer": payload.model_dump(mode="json"),
                        **fit_update,
                    },
                )
            return {
                **state,
                "status": "verified_partial",
                "detail": reason,
                "answer": AnswerPayload(
                    answer_text="Verified partial: answer generation stopped.",
                    status="partial",
                ).model_dump(mode="json"),
            }
        if needs_model:
            answer_calls = 1
    status = "answered"
    general_origins = {
        KnowledgeScope.GENERAL_KNOWLEDGE,
        KnowledgeScope.USER_SUPPLIED_TEXT,
        KnowledgeScope.DETERMINISTIC,
        KnowledgeScope.AMBIGUOUS,
    }
    if (
        answer.status == "refused"
        and not working_fusion.evidence
        and not working_tables
        and knowledge_scope not in general_origins
        and answer.answer_origin not in general_origins
    ):
        status = "insufficient_evidence"
    return cast(
        QueryGraphState,
        {
            **state,
            "status": status,
            "detail": "one answer generated from canonical evidence",
            "answer": answer.model_dump(mode="json"),
            "remaining_model_calls": remaining,
            "answer_call_count": answer_calls,
            "catalog_llm_call_count": int(state.get("catalog_llm_call_count") or 0),
            "keyword_extract_count": 0,
            **accumulated_tokens(
                state,
                added_prompt_tokens + locate_prompt_tokens,
                added_completion_tokens + locate_completion_tokens,
            ),
            **runtime_update,
            **fit_update,
            **locate_update,
        },
    )
