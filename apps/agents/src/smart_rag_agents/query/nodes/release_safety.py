"""Fail-closed release result for a checker or citation-persistence failure."""

from __future__ import annotations

from typing import cast

import psycopg
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import summarize_run_usage
from smart_rag_core.query_answer.models import AnswerPayload, VerificationResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.preparation import caller_from_runtime

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import runtime_from_state
from smart_rag_agents.query.state import QueryGraphState

VERIFICATION_UNAVAILABLE_TEXT = (
    "I could not verify this answer, so I have not released it. Please try again."
)


def refresh_refusal_usage(
    state: QueryGraphState, deps: QueryGraphDeps
) -> QueryGraphState:
    """Keep charged failed verifier attempts visible in final usage totals.

    Args:
        state: Safe refusal returned by the release boundary.
        deps: Scoped database connection, if available.

    Returns:
        The refusal with durable usage totals, or its conservative fallback
        counters when the usage store cannot be read. Never adds model work.
    """
    context = runtime_from_state(state)
    if deps.connection is None or context is None:
        return state
    try:
        usage = summarize_run_usage(
            deps.connection,
            caller=caller_from_runtime(context),
            run_id=context.run_id,
        )
    except (QueryAdmissionError, psycopg.Error):
        return state
    return {
        **state,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cost_usd": float(usage.cost_usd),
    }


def refuse_release(
    state: QueryGraphState,
    reason: str,
    *,
    remaining_model_calls: int | None = None,
    verifier_call_count: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> QueryGraphState:
    """Replace all draft claims/evidence with a typed, sanitized refusal.

    Args:
        state: Input state; never used as a source of public refusal prose.
        reason: Internal stable code or exception type, never its message.
        remaining_model_calls: Count after any attempted verifier call.
        verifier_call_count: Attempts already started, capped to one.
        prompt_tokens: Additional measured provider input tokens.
        completion_tokens: Additional measured provider output tokens.

    Returns:
        Refused state with an internally consistent answer/verification pair.
        Reservations/usage already recorded by a gateway remain untouched.
    """
    raw = state.get("answer")
    raw_origin = raw.get("answer_origin") if isinstance(raw, dict) else None
    try:
        origin = KnowledgeScope(raw_origin) if raw_origin else None
    except (TypeError, ValueError):
        origin = None
    safe_reason = "".join(c for c in reason if c.isalnum() or c == "_")[:64]
    safe_reason = safe_reason or "verification_failed"
    answer = AnswerPayload(
        answer_text=VERIFICATION_UNAVAILABLE_TEXT,
        answer_origin=origin,
        status="refused",
    )
    attempts = 1 if verifier_call_count else 0
    verification = VerificationResult(
        answer=answer,
        status="refused",
        deterministic_failures=(safe_reason,),
        verifier_call_count=attempts,
        verifier_skipped_reason=safe_reason,
    )
    return cast(
        QueryGraphState,
        {
            **state,
            "answer": answer.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json"),
            "status": "refused",
            "detail": f"verification_unavailable:{safe_reason}",
            "remaining_model_calls": (
                state["remaining_model_calls"]
                if remaining_model_calls is None
                else remaining_model_calls
            ),
            "verifier_call_count": attempts,
            "prompt_tokens": int(state.get("prompt_tokens") or 0) + prompt_tokens,
            "completion_tokens": int(state.get("completion_tokens") or 0)
            + completion_tokens,
        },
    )
