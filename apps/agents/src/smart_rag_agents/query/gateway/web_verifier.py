"""One durably counted semantic Web-release check; no answer retry."""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

from smart_rag_core.gateways.model import VerifierModelRequest
from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.versions import (
    WEB_VERIFIER_PROMPT_SHA256,
    WEB_VERIFIER_PROMPT_VERSION,
)
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.web_research.models import WebSourceRecord
from smart_rag_core.web_research.synthesis import isolate_web_sources

from smart_rag_agents.prompts.registry import prompt_text
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import gateway_timeout_seconds, run_coro
from smart_rag_agents.query.gateway.verifier import parse_verifier_payload
from smart_rag_agents.query.nodes.shared import (
    runtime_after_consume,
    runtime_from_state,
)
from smart_rag_agents.query.nodes.tokens import (
    accumulated_tokens,
    tokens_from_gateway_response,
)
from smart_rag_agents.query.state import QueryGraphState

_CHECKS = ("support", "coverage", "language", "references", "limitations")


def verify_web_answer(
    state: QueryGraphState,
    deps: QueryGraphDeps,
    answer: AnswerPayload,
    sources: tuple[WebSourceRecord, ...],
) -> AnswerPayload:
    """Fail closed on unsupported, wrong-language, malformed or unchecked prose."""
    context = runtime_from_state(state)
    if deps.model_gateway is None or context is None or deps.connection is None:
        raise AnswerError("web_verifier_unavailable")
    if state.get("verifier_call_count"):
        raise AnswerError("web_verifier_call_cap")
    remaining = assert_call_available(int(state.get("remaining_model_calls") or 0))
    cited = {item.web_source_id for item in answer.web_citations}
    selected = tuple(source for source in sources if source.web_source_id in cited)
    # Verify saved exact supporting spans, not unrelated page openings.
    selected = tuple(
        source.model_copy(
            update={
                "excerpt": "\n".join(
                    citation.span
                    for citation in answer.web_citations
                    if citation.web_source_id == source.web_source_id
                )
            }
        )
        for source in selected
    )
    records = json.dumps(
        {
            "original_question": state.get("user_query") or "",
            "draft": answer.answer_text,
            "citation_spans": [
                item.model_dump(mode="json") for item in answer.web_citations
            ],
            "evidence": isolate_web_sources(selected),
        },
        ensure_ascii=False,
    )
    if len(records) > deps.model_input_max_chars:
        raise AnswerError("web_verifier_input_bound")
    timeout = gateway_timeout_seconds(context)
    if timeout <= 0.2:
        raise AnswerError("web_verifier_deadline_exhausted")
    request = VerifierModelRequest(
        prompt_version=WEB_VERIFIER_PROMPT_VERSION,
        prompt_sha256=WEB_VERIFIER_PROMPT_SHA256,
        prompt_text=prompt_text(WEB_VERIFIER_PROMPT_VERSION),
        source_records=records,
        links=tuple({"link_id": check, "claim": check} for check in _CHECKS),
        remaining_deadline_seconds=min(8.0, timeout),
    )

    def consumed(value: ReservationConsumeResult) -> None:
        """Retain the consumed reservation version before sending provider work."""
        state["authorized_runtime"] = runtime_after_consume(context, value).model_dump(
            mode="json"
        )
        state["remaining_model_calls"] = remaining
        state["verifier_call_count"] = 1

    def send() -> object:
        """Send one bounded verifier attempt without retry or fallback prose."""
        try:
            return run_coro(
                lambda: cast(Any, deps.model_gateway).generate_verifier(request),
                cancel_check=deps.cancel_check,
                timeout_seconds=request.remaining_deadline_seconds,
            )
        except Exception as exc:
            raise TimeoutAfterSendError("web_verifier_unavailable") from exc

    response, _, _ = execute_counted_model_call(
        deps.connection,
        caller=caller_from_runtime(context),
        run_id=context.run_id,
        reservation_id=context.reservation_id,
        expected_version=context.optimistic_version,
        usage_kind="verifier",
        model_id=request.model_id,
        provider_attempt_id=str(uuid4()),
        send=send,
        on_consumed=consumed,
        usage_from_result=lambda value: (*tokens_from_gateway_response(value), None),
    )
    totals = accumulated_tokens(state, *tokens_from_gateway_response(response))
    state["prompt_tokens"] = totals["prompt_tokens"]
    state["completion_tokens"] = totals["completion_tokens"]
    payload = parse_verifier_payload(getattr(response, "payload", None))
    verdicts = {item.link_id: item.supported for item in payload.link_verdicts}
    if len(payload.link_verdicts) != len(_CHECKS) or set(verdicts) != set(_CHECKS):
        raise AnswerError("web_verifier_schema_invalid")
    if not all(
        verdicts[check]
        for check in ("support", "language", "references", "limitations")
    ):
        raise AnswerError("web_verifier_rejected")
    if not verdicts["coverage"]:
        # Only an already explicit partial may survive missing requirements.
        if answer.status != "partial":
            raise AnswerError("web_verifier_coverage_failed")
        return answer
    return answer
