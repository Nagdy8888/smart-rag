"""Observed provider usage survives bad output and never invents counters."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from smart_rag_agents.query.gateway.sync_bridge import run_coro
from smart_rag_core.gateways.openai_answer import (
    OpenAIAnswerError,
    parse_structured_response,
)
from smart_rag_core.gateways.provider_usage import (
    capture_provider_usage,
    observe_provider_response,
)
from smart_rag_core.query_admission.exceptions import TimeoutAfterSendError
from smart_rag_core.query_admission.usage import execute_counted_model_call


def response(**overrides: object) -> SimpleNamespace:
    """Return synthetic provider counters, including cached input and reasoning."""
    fields: dict[str, object] = {
        "input_tokens": 1000,
        "output_tokens": 100,
        "total_tokens": 1100,
        "input_tokens_details": SimpleNamespace(cached_tokens=500),
        "output_tokens_details": SimpleNamespace(reasoning_tokens=80),
    }
    fields.update(overrides)
    return SimpleNamespace(usage=SimpleNamespace(**fields), service_tier="default")


@pytest.mark.parametrize("failure", [False, True])
def test_counted_attempt_uses_returned_usage_even_if_output_is_invalid(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    """Failed parsing records real counts/cache price instead of timeout caps."""
    consume = Mock(return_value=SimpleNamespace(optimistic_version=2))
    record = Mock(return_value=uuid4())
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.consume_query_reservation", consume
    )
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage", record
    )

    def send() -> str:
        """Capture provider usage before returning or simulating send failure."""
        observe_provider_response(response())
        if failure:
            raise TimeoutAfterSendError("output_invalid")
        return "ok"

    kwargs = dict(
        caller=Mock(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        expected_version=1,
        usage_kind="answer",
        model_id="gpt-6-luna",
        provider_attempt_id="one",
        send=send,
    )
    if failure:
        with pytest.raises(TimeoutAfterSendError):
            execute_counted_model_call(Mock(), **kwargs)  # type: ignore[arg-type]
    else:
        execute_counted_model_call(Mock(), **kwargs)  # type: ignore[arg-type]
    record.assert_called_once()
    row = record.call_args.kwargs
    assert row["prompt_tokens"] == 1000
    assert row["completion_tokens"] == 100  # reasoning is already included
    assert row["cached_prompt_tokens"] == 500
    assert row["estimated_cost_usd"] == Decimal("0.00010500")
    assert row["timeout_after_send"] is False


@pytest.mark.parametrize("value", [None, -1, True, "1000"])
def test_invalid_provider_counters_are_not_measured(value: object) -> None:
    """Malformed counts cannot become zero-token measured calls."""
    with capture_provider_usage() as observed:
        observe_provider_response(response(input_tokens=value))
        assert observed == []


def test_capture_precedes_status_and_json_validation() -> None:
    """An incomplete response can still contain trustworthy billable counters."""
    raw = response()
    raw.status = "incomplete"
    with capture_provider_usage() as observed:
        with pytest.raises(OpenAIAnswerError):
            parse_structured_response(raw, kind="answer")
        assert len(observed) == 1
        assert observed[0].output_tokens == 100


def test_capture_survives_sync_bridge_and_does_not_leak_between_attempts() -> None:
    """Copied thread/async contexts share only their own mutable collector."""

    async def gateway() -> str:
        """Observe usage inside the asynchronous gateway context."""
        observe_provider_response(response())
        return "ok"

    async def invoke() -> None:
        """Check that the synchronous bridge preserves the active collector."""
        with capture_provider_usage() as observed:
            assert run_coro(gateway) == "ok"
            assert len(observed) == 1

    asyncio.run(invoke())
    with capture_provider_usage() as observed:
        assert observed == []


@pytest.mark.parametrize("tier,written", [("unknown-tier", 0), ("default", 10)])
def test_unpriced_processing_keeps_counts_but_does_not_invent_cost(
    monkeypatch: pytest.MonkeyPatch, tier: str, written: int
) -> None:
    """Unsupported tier/cache-write prices remain explicitly unresolved."""
    from smart_rag_core.query_admission.usage import record_observed_usage

    record = Mock(return_value=uuid4())
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage", record
    )
    raw = response(
        input_tokens_details=SimpleNamespace(
            cached_tokens=500, cache_write_tokens=written
        )
    )
    raw.service_tier = tier
    with capture_provider_usage() as observed:
        observe_provider_response(raw)
        record_observed_usage(
            Mock(),
            caller=Mock(),
            run_id=uuid4(),
            reservation_id=uuid4(),
            reservation_version=2,
            usage_kind="answer",
            model_id="gpt-6-luna",
            provider_attempt_id="one",
            observed=observed[0],
            usd_cap=Decimal("0.4"),
        )
    assert record.call_args.kwargs["estimated_cost_usd"] is None
    assert record.call_args.kwargs["provider_prompt_tokens"] == 1000
    assert record.call_args.kwargs["cost_basis"] == "safety_allowance"


def test_sdk_extra_mapping_preserves_cache_write_lifetimes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Older SDKs keep new nested usage fields as dictionaries, not models."""
    from openai.types.responses.response_usage import InputTokensDetails
    from smart_rag_core.query_admission.usage import record_observed_usage

    details = InputTokensDetails.model_validate(
        {
            "cached_tokens": 200,
            "cache_write_tokens": 500,
            "cache_write_tokens_details": {
                "ttl_30m_tokens": 300,
                "ttl_12h_tokens": 200,
            },
        }
    )
    assert isinstance((details.model_extra or {})["cache_write_tokens_details"], dict)
    raw = response(input_tokens_details=details)
    record = Mock(return_value=uuid4())
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage", record
    )
    with capture_provider_usage() as observed:
        observe_provider_response(raw)
        assert observed[0].cache_write_30m_tokens == 300
        assert observed[0].cache_write_12h_tokens == 200
        record_observed_usage(
            Mock(),
            caller=Mock(),
            run_id=uuid4(),
            reservation_id=uuid4(),
            reservation_version=2,
            usage_kind="answer",
            model_id="gpt-6-luna",
            provider_attempt_id="sdk-mapping",
            observed=observed[0],
            usd_cap=Decimal("0.40"),
        )
    assert record.call_args.kwargs["estimated_cost_usd"] == Decimal("0.00016950")
    assert record.call_args.kwargs["cost_basis"] == "standard_token_estimate"
