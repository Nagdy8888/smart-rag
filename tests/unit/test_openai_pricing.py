"""OpenAI list-price usage estimates."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from smart_rag_core.gateways.openai_pricing import (
    estimate_chat_cost_usd,
    estimate_embedding_cost_usd,
    estimate_usage_cost_usd,
)
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_admission.usage import execute_counted_model_call


def test_estimate_chat_cost_matches_gpt4o_mini_list_price() -> None:
    """Typical answer-call tokens should cost fractions of a cent, not caps."""

    cost = estimate_chat_cost_usd(prompt_tokens=3291, completion_tokens=147)
    assert cost == Decimal("0.00058185")


def test_estimate_embedding_cost_matches_large_model_list_price() -> None:
    """Embedding batches bill input tokens only."""

    cost = estimate_embedding_cost_usd(prompt_tokens=512)
    assert cost == Decimal("0.00006656")


def test_estimate_usage_cost_routes_by_kind() -> None:
    """Embedding kinds use the embedding rate."""

    assert estimate_usage_cost_usd(
        usage_kind="embedding",
        model_id="text-embedding-3-large",
        prompt_tokens=1000,
        completion_tokens=0,
    ) == Decimal("0.00013000")
    assert estimate_usage_cost_usd(
        usage_kind="answer",
        model_id="gpt-4o-mini",
        prompt_tokens=1000,
        completion_tokens=100,
    ) == Decimal("0.00021000")


def test_execute_counted_model_call_records_token_priced_usd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful sends record list-price USD instead of the answer cap."""

    recorded: dict[str, object] = {}

    def _fake_record(_connection: object, **kwargs: object) -> object:
        """Capture billed kwargs from ``record_query_llm_usage``.

        Args:
            _connection: Unused database connection.
            **kwargs: Recorded usage fields.

        Returns:
            Unused sentinel object.
        """

        recorded.update(kwargs)
        return object()

    def _fake_consume(*args: object, **kwargs: object) -> ReservationConsumeResult:
        """Return a consume snapshot with remaining budget.

        Args:
            *args: Unused positional arguments from the patched call.
            **kwargs: Unused keyword arguments from the patched call.

        Returns:
            Consume result with remaining USD above the answer cap.
        """

        del args, kwargs
        return ReservationConsumeResult(
            reservation_id=UUID("00000000-0000-0000-0000-000000000001"),
            optimistic_version=2,
            remaining_usd=Decimal("1"),
            remaining_prompt_tokens=10_000,
            remaining_completion_tokens=10_000,
        )

    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.consume_query_reservation",
        _fake_consume,
    )
    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.record_query_llm_usage",
        _fake_record,
    )

    execute_counted_model_call(
        object(),  # type: ignore[arg-type]
        caller=object(),  # type: ignore[arg-type]
        run_id=object(),  # type: ignore[arg-type]
        reservation_id=object(),  # type: ignore[arg-type]
        expected_version=1,
        usage_kind="answer",
        model_id="gpt-4o-mini",
        provider_attempt_id="attempt-1",
        send=lambda: "ok",
        usage_from_result=lambda _result: (3291, 147, None),
    )

    assert recorded["prompt_tokens"] == 3291
    assert recorded["completion_tokens"] == 147
    assert recorded["cost_usd"] == Decimal("0.00058185")
