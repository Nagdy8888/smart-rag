"""One durably accounted Web synthesis attempt within the admitted run."""

from uuid import uuid4

from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.versions import ANSWER_MODEL_ID
from smart_rag_core.query_routing.preparation import caller_from_runtime
from smart_rag_core.web_research.models import WebSourceRecord

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.web_answer import gateway_web_answer
from smart_rag_agents.query.nodes.shared import (
    runtime_after_consume,
    runtime_from_state,
)
from smart_rag_agents.query.nodes.tokens import accumulated_tokens
from smart_rag_agents.query.state import QueryGraphState


def counted_web_answer(
    state: QueryGraphState,
    deps: QueryGraphDeps,
    *,
    query: str,
    sources: tuple[WebSourceRecord, ...],
) -> AnswerPayload:
    """Reserve, call once, record usage, and retain consumed state on failure."""
    context = runtime_from_state(state)
    if context is None or deps.connection is None:
        raise AnswerError("web_runtime_unavailable")
    remaining = assert_call_available(int(state.get("remaining_model_calls") or 0))

    def on_consumed(consumed: ReservationConsumeResult) -> None:
        """Keep the next node on the actual reservation version, even on error."""
        state["authorized_runtime"] = runtime_after_consume(
            context, consumed
        ).model_dump(mode="json")
        state["remaining_model_calls"] = remaining

    def send() -> tuple[AnswerPayload, int, int]:
        """Surface provider failure rather than releasing a mock answer."""
        try:
            return gateway_web_answer(
                deps, query=query, sources=sources, context=context
            )
        except AnswerError as exc:
            if exc.reason in {
                "web_answer_input_bound",
                "web_answer_sources_empty",
                "web_answer_prompt_unbound",
                "model_gateway_unbound",
                "input_bound_exceeded",
            }:
                # These checks happen before a provider send, so no usage exists.
                raise
            # Missing usage after an attempted send must keep the safety allowance.
            raise TimeoutAfterSendError("web_answer_unavailable") from exc

    result, _, _ = execute_counted_model_call(
        deps.connection,
        caller=caller_from_runtime(context),
        run_id=context.run_id,
        reservation_id=context.reservation_id,
        expected_version=context.optimistic_version,
        usage_kind="answer",
        model_id=ANSWER_MODEL_ID,
        provider_attempt_id=str(uuid4()),
        send=send,
        on_consumed=on_consumed,
        usage_from_result=lambda result: (
            result[1] if result[1] > 0 else None,
            result[2] if result[1] > 0 else None,
            None,
        ),
    )
    totals = accumulated_tokens(state, result[1], result[2])
    state["prompt_tokens"] = totals["prompt_tokens"]
    state["completion_tokens"] = totals["completion_tokens"]
    return result[0]
