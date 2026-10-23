"""At most two counted answer attempts inside the run deadline."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID, uuid4

from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import (
    QueryCeilingError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.exceptions import AnswerError

from smart_rag_agents.query.nodes.shared import runtime_after_consume
from smart_rag_agents.query.run_timings import (
    classify_attempt_outcome,
    with_answer_attempt,
)
from smart_rag_agents.query.state import QueryGraphState

ANSWER_ATTEMPT_CAP_SECONDS = 15.0
"""Per-attempt cap until a measured 99th percentile replaces it."""

ANSWER_RETRY_MIN_REMAINING_SECONDS = 8.0
"""Do not start a second attempt with less than this much run time left."""

_RETRYABLE = frozenset({"answer_timeout", "answer_provider_error", "gateway_failed"})

T = TypeVar("T")


class _CountedAnswerFailure(TimeoutAfterSendError):
    """Invalid received provider output still represents a charged attempt."""

    def __init__(self, reason: str) -> None:
        """Preserve a stable error code without raw provider output."""
        super().__init__(reason)
        self.reason = reason


def run_answer_attempts(
    state: QueryGraphState,
    *,
    connection: object,
    caller: object,
    run_id: object,
    reservation_id: object,
    expected_version: int,
    model_id: str,
    send: Callable[[], T],
    usage_from_result: Callable[[T], tuple[int | None, int | None, object]],
    context: AuthorizedRuntimeContext | None,
    remaining_model_calls: int,
) -> tuple[T, ReservationConsumeResult, UUID, int]:
    """Send the answer at most twice.

    Args:
        state: Graph state. ``run_timings`` is updated in place.
        connection: Canonical connection for the counted usage write.
        caller: Server-derived caller.
        run_id: Admitted run id.
        reservation_id: Run-local reservation.
        expected_version: Optimistic reservation version.
        model_id: Pinned answer model.
        send: One provider call. Invoked again only on a retry.
        usage_from_result: Reads provider token counts from a success.
        context: Admitted runtime, used for the retry deadline check.
        remaining_model_calls: Calls left after the first attempt was reserved.

    Returns:
        Gateway result, consumed reservation, usage id, and the model-call
        count left after every attempt that was reserved.

    Raises:
        AnswerError: Non-retryable provider failure, or the last retryable
            failure when a second attempt is not allowed.
        TimeoutAfterSendError: The last attempt was sent and then lost.
        QueryCeilingError: The reservation or ceiling rejects the call.
        QueryBudgetError: The reservation cannot cover the cap.

    Side Effects:
        Each attempt consumes reservation and writes ``llm_usage``, including
        a timeout after the request was sent.
    """

    remaining = remaining_model_calls

    def consumed_snapshot(consumed: ReservationConsumeResult) -> None:
        """Keep retry and fallback verification on the consumed version."""
        nonlocal expected_version
        expected_version = consumed.optimistic_version
        if context is not None:
            state["authorized_runtime"] = runtime_after_consume(
                context, consumed
            ).model_dump(mode="json")
        state["remaining_model_calls"] = remaining

    def counted_send() -> T:
        """Charge received-but-invalid answers conservatively without retrying."""
        try:
            return send()
        except AnswerError as exc:
            if exc.reason in {
                "answer_incomplete",
                "answer_schema_invalid",
                "answer_unknown_usage",
            }:
                raise _CountedAnswerFailure(exc.reason) from exc
            raise

    last: BaseException | None = None
    for index in range(2):
        if index:
            if not _retry_allowed(context, remaining):
                break
            try:
                remaining = assert_call_available(remaining)
            except QueryCeilingError:
                break
        started = time.perf_counter()
        try:
            counted, consumed, usage_id = execute_counted_model_call(
                connection,  # type: ignore[arg-type]
                caller=caller,  # type: ignore[arg-type]
                run_id=run_id,  # type: ignore[arg-type]
                reservation_id=reservation_id,  # type: ignore[arg-type]
                expected_version=expected_version,
                usage_kind="answer",
                model_id=model_id,
                provider_attempt_id=str(uuid4()),
                send=counted_send,
                usage_from_result=usage_from_result,  # type: ignore[arg-type]
                on_consumed=consumed_snapshot,
            )
        except TimeoutAfterSendError as exc:
            reason = (
                exc.reason
                if isinstance(exc, _CountedAnswerFailure)
                else "timeout_after_send"
            )
            _record(state, started, "timeout_after_send", reason)
            last = exc
            if isinstance(exc, _CountedAnswerFailure):
                break
            continue
        except AnswerError as exc:
            outcome = classify_attempt_outcome(exc.reason)
            _record(state, started, outcome, exc.reason)
            if exc.reason not in _RETRYABLE:
                raise
            last = exc
            continue
        _record(state, started, "ok", "")
        return counted, consumed, usage_id, remaining
    if isinstance(last, TimeoutAfterSendError):
        raise last
    if isinstance(last, AnswerError):
        raise last
    raise AnswerError("gateway_failed")


def _retry_allowed(
    context: AuthorizedRuntimeContext | None,
    remaining_model_calls: int,
) -> bool:
    """Return whether a second attempt still fits the deadline and ceiling.

    Args:
        context: Admitted runtime.
        remaining_model_calls: Calls left before reserving the retry.

    Returns:
        True when at least eight seconds and one model call remain.
    """

    if remaining_model_calls < 1 or context is None:
        return False
    left = (context.deadline_at - datetime.now(UTC)).total_seconds()
    return left >= ANSWER_RETRY_MIN_REMAINING_SECONDS


def _record(
    state: QueryGraphState,
    started: float,
    outcome: str,
    reason: str,
) -> None:
    """Store one attempt on ``state['run_timings']``.

    Args:
        state: Graph state mutated in place.
        started: ``time.perf_counter`` at the attempt start.
        outcome: Allow-listed attempt outcome.
        reason: Safe reason code.
    """

    update = with_answer_attempt(
        state,
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        outcome=outcome,  # type: ignore[arg-type]
        reason=reason,
    )
    timings = update["run_timings"]
    state["run_timings"] = timings if isinstance(timings, dict) else None
