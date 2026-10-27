"""Termination summary payload for one finished SSE executor stream."""

from __future__ import annotations

from typing import cast

from smart_rag_api.services.sse.chunks import coerce_stream_token_count


def build_termination_payload(
    summary: object,
    *,
    cancelled: bool,
    assistant_parts: list[str],
    prompt_tokens: int | None,
    completion_tokens: int | None,
    usage_reporting: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the executor's termination payload with token and cost totals.

    Token counts seen on ``usage`` events win. Missing counts fall back to
    the executor summary (``input_tokens`` then ``prompt_tokens``, and
    ``output_tokens`` then ``completion_tokens``). When any count is known,
    both totals, ``total_tokens``, and an estimated USD cost are set.

    Args:
        summary: The executor's ``termination_summary``. Anything that is not
            a dict is replaced by a minimal summary.
        cancelled: Whether the run's cancel event is set.
        assistant_parts: Streamed ``token_delta`` texts in order.
        prompt_tokens: Last prompt-token count from ``usage`` events.
        completion_tokens: Last completion-token count from ``usage`` events.
        usage_reporting: Authoritative per-operation projection when available.

    Returns:
        A new payload dict. ``summary`` is not modified.
    """

    payload: dict[str, object]
    if isinstance(summary, dict):
        typed_summary = cast(dict[object, object], summary)
        payload = {str(key): value for key, value in typed_summary.items()}
    else:
        payload = {
            "termination_reason": "cancelled" if cancelled else "unknown",
            "terminal_event_type": None,
            "stream_exhausted": False,
        }
    if assistant_parts:
        payload["assistant_message"] = "".join(assistant_parts)
    if prompt_tokens is None:
        prompt_tokens = coerce_stream_token_count(payload.get("input_tokens"))
    if prompt_tokens is None:
        prompt_tokens = coerce_stream_token_count(payload.get("prompt_tokens"))
    if completion_tokens is None:
        completion_tokens = coerce_stream_token_count(payload.get("output_tokens"))
    if completion_tokens is None:
        completion_tokens = coerce_stream_token_count(payload.get("completion_tokens"))
    if prompt_tokens is not None:
        payload["input_tokens"] = prompt_tokens
    if completion_tokens is not None:
        payload["output_tokens"] = completion_tokens
    input_count = coerce_stream_token_count(payload.get("input_tokens"))
    output_count = coerce_stream_token_count(payload.get("output_tokens"))
    if input_count is not None or output_count is not None:
        from smart_rag_core.observability.langsmith_tracing import (
            estimate_traced_chat_cost_usd,
        )

        input_total = 0 if input_count is None else input_count
        output_total = 0 if output_count is None else output_count
        payload["input_tokens"] = input_total
        payload["output_tokens"] = output_total
        payload["total_tokens"] = input_total + output_total
        payload["estimated_cost_usd"] = float(
            estimate_traced_chat_cost_usd(
                input_tokens=input_total,
                output_tokens=output_total,
            )
        )
    if usage_reporting is not None:
        # Mixed-model aggregate counts cannot be priced as one answer call.
        estimate = usage_reporting.get("estimated_cost_usd")
        payload["usage_cost_status"] = (
            "reported" if estimate is not None else "unresolved"
        )
        if estimate is None:
            payload.pop("estimated_cost_usd", None)
        else:
            payload["estimated_cost_usd"] = float(str(estimate))
    return payload
