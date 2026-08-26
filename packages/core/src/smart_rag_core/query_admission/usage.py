"""Counted gateway consume plus immutable usage recording."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

import psycopg

from smart_rag_core.query_admission.ceilings import usage_kind_caps
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_admission.service import (
    ReservationConsumeResult,
    consume_query_reservation,
    record_query_llm_usage,
)
from smart_rag_core.security.identity import CallerContext

T = TypeVar("T")


def execute_counted_model_call(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    reservation_id: UUID,
    expected_version: int,
    usage_kind: str,
    model_id: str,
    provider_attempt_id: str,
    send: Callable[[], T],
    actual_prompt_tokens: int | None = None,
    actual_completion_tokens: int | None = None,
    actual_cost_usd: Decimal | None = None,
    usage_from_result: Callable[[T], tuple[int | None, int | None, Decimal | None]]
    | None = None,
) -> tuple[T, ReservationConsumeResult, UUID]:
    """Consume the run-local reservation, invoke one provider attempt, record usage.

    Crash before ``send`` records no usage. Timeout-after-send still writes
    immutable usage using the kind's conservative cap so the attempt cannot
    be under-counted. Shared company/user budget rows are not locked.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived run owner.
        run_id: Admitted query run.
        reservation_id: Run-local reservation.
        expected_version: Optimistic version to consume.
        usage_kind: Allow-listed usage kind.
        model_id: Provider model identifier.
        provider_attempt_id: Idempotent attempt identifier.
        send: Provider invocation. Raise ``TimeoutAfterSendError`` after send.
        actual_prompt_tokens: Tokens known before ``send``. Prefer
            ``usage_from_result`` when the provider reports usage on the
            response.
        actual_completion_tokens: Tokens known before ``send``.
        actual_cost_usd: Measured USD known before ``send``.
        usage_from_result: Optional extractor run after a successful
            ``send``. Non-null extracted values override the ``actual_*``
            arguments. Timeout-after-send still records the conservative
            cap and does not call this extractor.

    Returns:
        Provider result, consume snapshot, and ``llm_usage.id``.

    Raises:
        QueryBudgetError: When remaining reservation cannot cover the cap.
        QueryCeilingError: When the usage kind is unknown.
        TimeoutAfterSendError: Re-raised after usage is recorded.
        Exception: Re-raised when ``send`` fails before a sent attempt.
            No usage row is written in that case.

    Side Effects:
        Decrements remaining reservation, then inserts ``llm_usage`` for
        successful and timeout-after-send attempts.
    """

    usd_cap, prompt_cap, completion_cap = usage_kind_caps(usage_kind)
    consumed = consume_query_reservation(
        connection,
        caller=caller,
        reservation_id=reservation_id,
        expected_version=expected_version,
        amount_usd=usd_cap,
        prompt_tokens=prompt_cap,
        completion_tokens=completion_cap,
    )
    try:
        result = send()
    except TimeoutAfterSendError:
        record_query_llm_usage(
            connection,
            caller=caller,
            run_id=run_id,
            reservation_id=reservation_id,
            reservation_version=consumed.optimistic_version,
            usage_kind=usage_kind,
            model_id=model_id,
            provider_attempt_id=provider_attempt_id,
            prompt_tokens=prompt_cap,
            completion_tokens=completion_cap,
            cost_usd=usd_cap,
            timeout_after_send=True,
        )
        raise
    recorded_prompt = actual_prompt_tokens
    recorded_completion = actual_completion_tokens
    recorded_cost = actual_cost_usd
    if usage_from_result is not None:
        extracted_prompt, extracted_completion, extracted_cost = usage_from_result(
            result
        )
        if extracted_prompt is not None:
            recorded_prompt = extracted_prompt
        if extracted_completion is not None:
            recorded_completion = extracted_completion
        if extracted_cost is not None:
            recorded_cost = extracted_cost
    usage_id = record_query_llm_usage(
        connection,
        caller=caller,
        run_id=run_id,
        reservation_id=reservation_id,
        reservation_version=consumed.optimistic_version,
        usage_kind=usage_kind,
        model_id=model_id,
        provider_attempt_id=provider_attempt_id,
        prompt_tokens=(recorded_prompt if recorded_prompt is not None else prompt_cap),
        completion_tokens=(
            recorded_completion if recorded_completion is not None else completion_cap
        ),
        cost_usd=recorded_cost if recorded_cost is not None else usd_cap,
        timeout_after_send=False,
    )
    return result, consumed, usage_id
