"""Termination payload built after an SSE executor stream ends."""

from __future__ import annotations

from smart_rag_api.services.sse.run_summary import build_termination_payload


def test_operation_cost_projection_wins_over_mixed_model_token_repricing() -> None:
    """Parent traces must use the ledger projection, including cache discounts."""
    payload = build_termination_payload(
        None,
        cancelled=False,
        assistant_parts=[],
        prompt_tokens=1000,
        completion_tokens=100,
        usage_reporting={"estimated_cost_usd": "0.00010500"},
    )
    assert payload["estimated_cost_usd"] == 0.000105


def test_unknown_reported_cost_stays_unknown_through_trace_redaction() -> None:
    """Unknown usage cannot become a default-model charge on a parent span."""
    from smart_rag_core.observability.query_trace.redaction import (
        redact_query_run_sse_outputs,
    )

    payload = build_termination_payload(
        None,
        cancelled=False,
        assistant_parts=[],
        prompt_tokens=1000,
        completion_tokens=100,
        usage_reporting={"estimated_cost_usd": None},
    )
    assert "estimated_cost_usd" not in payload
    redacted = redact_query_run_sse_outputs(payload)
    assert "estimated_cost_usd" not in redacted
    assert redacted["usage_cost_status"] == "unresolved"


def test_non_dict_summary_becomes_minimal_payload() -> None:
    """A missing executor summary yields reason, terminal type, and no tokens."""

    payload = build_termination_payload(
        None,
        cancelled=True,
        assistant_parts=[],
        prompt_tokens=None,
        completion_tokens=None,
    )

    assert payload == {
        "termination_reason": "cancelled",
        "terminal_event_type": None,
        "stream_exhausted": False,
    }


def test_usage_counts_win_and_cost_is_estimated() -> None:
    """``usage`` counts override the summary and set totals and cost."""

    summary: dict[str, object] = {
        "termination_reason": "completed",
        "input_tokens": 1,
        "output_tokens": 2,
    }

    payload = build_termination_payload(
        summary,
        cancelled=False,
        assistant_parts=["Hello ", "world"],
        prompt_tokens=100,
        completion_tokens=40,
    )

    assert payload["assistant_message"] == "Hello world"
    assert payload["input_tokens"] == 100
    assert payload["output_tokens"] == 40
    assert payload["total_tokens"] == 140
    cost = payload["estimated_cost_usd"]
    assert isinstance(cost, float)
    assert cost >= 0.0
    assert summary["input_tokens"] == 1


def test_summary_counts_fill_missing_usage_counts() -> None:
    """Without ``usage`` counts, the summary's prompt/completion names count."""

    payload = build_termination_payload(
        {"prompt_tokens": 7, "completion_tokens": 3},
        cancelled=False,
        assistant_parts=[],
        prompt_tokens=None,
        completion_tokens=None,
    )

    assert payload["input_tokens"] == 7
    assert payload["output_tokens"] == 3
    assert payload["total_tokens"] == 10
