"""Checkpoint recovery preserves stored counts without duplicate snapshot billing."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from smart_rag_core.observability.checkpoint_usage import (
    deduplicate_checkpoint_usage,
    recover_usage_candidate,
)


def test_repeated_snapshots_are_not_summed_and_a_later_reset_does_not_erase_usage() -> (
    None
):
    """One run can have many state saves; choose its latest nonzero counters."""
    runtime = {"run_id": str(uuid4()), "user_id": str(uuid4())}
    now = datetime.now(UTC)
    rows = [
        recover_usage_candidate(
            runtime,
            {"prompt_tokens": prompt, "completion_tokens": output, "cost_usd": "0.001"},
            checkpoint_id=str(index),
            recorded_at=now + timedelta(seconds=index),
        )
        for index, (prompt, output) in enumerate(
            [(100, 10), (100, 10), (150, 20), (0, 0)]
        )
    ]
    recovered = deduplicate_checkpoint_usage(row for row in rows if row is not None)
    assert len(recovered) == 1
    assert recovered[0].prompt_tokens == 150
    assert recovered[0].completion_tokens == 20
    assert recovered[0].estimated_cost_usd == Decimal("0.001")


@pytest.mark.parametrize("cost", ["0.02", "0.4", "0.403206"])
def test_allowance_like_stored_costs_remain_unresolved(cost: str) -> None:
    """Do not present conservative accounting allowances as provider spending."""
    row = recover_usage_candidate(
        {"run_id": str(uuid4()), "user_id": str(uuid4())},
        {"prompt_tokens": 8000, "completion_tokens": 2000, "cost_usd": cost},
        checkpoint_id="snapshot",
        recorded_at=datetime.now(UTC),
    )
    assert row is not None
    assert row.stored_cost_usd == Decimal(cost)
    assert row.estimated_cost_usd is None
    assert row.cost_state == "allowance_possible"


@pytest.mark.parametrize("tokens", [True, -1, "123", None])
def test_invalid_counters_cannot_become_recovered_usage(tokens: object) -> None:
    """Malformed counters must not be coerced to plausible measurements."""
    assert (
        recover_usage_candidate(
            {"run_id": str(uuid4()), "user_id": str(uuid4())},
            {"prompt_tokens": tokens, "completion_tokens": 1, "cost_usd": None},
            checkpoint_id="snapshot",
            recorded_at=datetime.now(UTC),
        )
        is None
    )


def test_unknown_only_history_is_not_a_zero_dollar_total() -> None:
    """An empty ledger cannot turn a missing historical charge into free usage."""
    from smart_rag_core.observability.checkpoint_usage import (
        CheckpointUsageSummary,
        combined_usage_cost,
    )

    history = CheckpointUsageSummary(
        runs=1,
        prompt_tokens=100,
        completion_tokens=10,
        estimated_cost_usd=None,
        unpriced_runs=1,
        overlapping_ledger_runs=0,
        additional_prompt_tokens=100,
        additional_completion_tokens=10,
        additional_estimated_cost_usd=None,
        first_recorded_at=None,
        last_recorded_at=None,
    )
    assert combined_usage_cost(Decimal(0), history) is None
    assert combined_usage_cost(Decimal(0), history, ledger_operations=1) == 0
