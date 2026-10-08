"""At most two counted answer attempts inside the run deadline."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid4

from smart_rag_core.query_admission.ceilings import assert_call_available
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import (
    QueryCeilingError,
    TimeoutAfterSendError,
)
from smart_rag_core.query_admission.usage import execute_counted_model_call
from smart_rag_core.query_answer.exceptions import AnswerError

from smart_rag_agents.query.run_timings import (
    classify_attempt_outcome,
    with_answer_attempt,
)

ANSWER_ATTEMPT_CAP_SECONDS = 10.0
"""Per-attempt cap until a measured 99th percentile replaces it."""

ANSWER_RETRY_MIN_REMAINING_SECONDS = 8.0
"""Do not start a second attempt with less than this much run time left."""

_RETRYABLE = frozenset({"answer_timeout", "answer_provider_error", "gateway_failed"})

T = TypeVar("T")


def run_answer_attempts(
    state: dict[str, object],
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
) -> tuple[T, object, object, int]:
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
                send=send,
                usage_from_result=usage_from_result,  # type: ignore[arg-type]
            )
        except TimeoutAfterSendError as exc:
            _record(state, started, "timeout_after_send", "timeout_after_send")
            last = exc
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
    state: dict[str, object],
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
    state["run_timings"] = update["run_timings"]
