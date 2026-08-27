"""Deterministic citation checks, then at most one six-link verifier call."""

from __future__ import annotations

from typing import cast

import psycopg
from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.service import summarize_run_usage
from smart_rag_core.query_answer.citations import (
    ensure_fusion_source_citations,
    maybe_persist_verified_citations,
)
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
    VerificationResult,
    VerifierPayload,
)
from smart_rag_core.query_answer.verifier import run_verifier_batch
from smart_rag_core.query_routing.constants import (
    FALLBACK_RETRIEVERS_UNBOUND,
    LIMITATION_VERIFIER_OMITTED_LINKS,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.query_routing.serde import plan_from_state

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.verifier import gateway_verifier
from smart_rag_agents.query.nodes.shared import (
    route_needs_retrieval,
    runtime_from_state,
    skip_closed_nodes,
)
from smart_rag_agents.query.nodes.state_codec import (
    fusion_from_state,
    tables_from_state,
)
from smart_rag_agents.query.state import QueryGraphState


def verify_answer_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Deterministic citation checks, then at most one six-link verifier call.

    State inputs:
        ``answer``, ``fusion``, ``table_composition``,
        ``remaining_model_calls``, ``verifier_call_count``.

    State outputs:
        ``verification``, accumulated ``prompt_tokens`` /
        ``completion_tokens``, and possibly decremented remaining calls.

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
        Missing gateway or omitted verifier links never terminate
        ``verified``. Omitted IDs force ``verified_partial`` and
        ``verifier_omitted_links``.

    Args:
        state: State after answer generation.
        deps: Optional gateway and connection.

    Returns:
        Terminal verified state.
    """

    if skip_closed_nodes(state):
        return state
    fusion = fusion_from_state(state.get("fusion"))
    tables = tables_from_state(state.get("table_composition"))
    raw_answer = state.get("answer")
    if raw_answer is None:
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": "missing_answer",
        }
    payload = AnswerPayload.model_validate(raw_answer)
    plan = None
    if state.get("retrieval_plan") is not None:
        try:
            plan = plan_from_state(state["retrieval_plan"])
        except ValueError:
            plan = None
    checked, failures = deterministic_check_answer(
        payload,
        fusion=fusion,
        tables=tables.records,
        evidence_required=route_needs_retrieval(plan),
    )
    remaining = state["remaining_model_calls"]
    verifier_calls = state.get("verifier_call_count") or 0
    omitted: tuple[str, ...] = ()
    added_prompt_tokens = 0
    added_completion_tokens = 0
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

                nonlocal added_prompt_tokens, added_completion_tokens
                payload, prompt_tokens, completion_tokens = gateway_verifier(
                    deps,
                    links=links,
                    fusion=fusion,
                    tables=tables.records,
                    context=runtime_from_state(state),
                )
                added_prompt_tokens += prompt_tokens
                added_completion_tokens += completion_tokens
                return payload

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
    knowledge_scope = plan.knowledge_scope if plan is not None else None
    terminal = "verified_partial"
    if (
        checked.status == "refused"
        and not fusion.evidence
        and not tables.records
        and knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    ):
        terminal = "insufficient_evidence"
        detail = "insufficient authorized evidence"
    elif checked.status == "refused":
        terminal = "refused"
        detail = "answer refused after verification"
    elif checked.status == "partial" or failures or omitted:
        terminal = "verified_partial"
        detail = (
            LIMITATION_VERIFIER_OMITTED_LINKS
            if omitted
            else "verified partial after citation checks"
        )
    else:
        terminal = "verified"
        detail = "answer verified"
    if (
        terminal == "verified"
        and deps.model_gateway is None
        and route_needs_retrieval(plan)
    ):
        terminal = "verified_partial"
        detail = "model_gateway_unbound"
    if (
        terminal == "verified"
        and route_needs_retrieval(plan)
        and deps.hybrid_retriever is None
    ):
        terminal = "insufficient_evidence"
        detail = FALLBACK_RETRIEVERS_UNBOUND
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
    context = runtime_from_state(state)
    billed_prompt = int(state.get("prompt_tokens") or 0) + max(0, added_prompt_tokens)
    billed_completion = int(state.get("completion_tokens") or 0) + max(
        0, added_completion_tokens
    )
    billed_cost_usd: float | None = None
    if deps.connection is not None and context is not None:
        try:
            billed = summarize_run_usage(
                deps.connection,
                caller=caller_from_runtime(context),
                run_id=context.run_id,
            )
            billed_prompt = billed.prompt_tokens
            billed_completion = billed.completion_tokens
            billed_cost_usd = float(billed.cost_usd)
        except (QueryAdmissionError, psycopg.Error):
            pass
    checked = ensure_fusion_source_citations(
        checked,
        fusion=fusion,
        tables=tables.records,
    )
    if route_needs_retrieval(plan) and checked.answer_origin is None:
        checked = checked.model_copy(
            update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
        )
    maybe_persist_verified_citations(
        deps.connection,
        caller=caller_from_runtime(context) if context is not None else None,
        run_id=context.run_id if context is not None else None,
        fusion=fusion,
        answer=checked,
    )
    return cast(
        QueryGraphState,
        {
            **state,
            "status": terminal,
            "detail": detail,
            "answer": checked.model_dump(mode="json"),
            "verification": result.model_dump(mode="json"),
            "remaining_model_calls": remaining,
            "verifier_call_count": verifier_calls,
            "catalog_llm_call_count": int(state.get("catalog_llm_call_count") or 0),
            "keyword_extract_count": 0,
            "prompt_tokens": billed_prompt,
            "completion_tokens": billed_completion,
            "cost_usd": billed_cost_usd,
        },
    )
