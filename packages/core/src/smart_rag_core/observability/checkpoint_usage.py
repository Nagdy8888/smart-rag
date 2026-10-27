"""Content-free checkpoint usage recovery, separate from budget accounting."""

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from smart_rag_core.query_admission.usage_caps import USAGE_KIND_USD_CAPS


class CheckpointUsageRun(BaseModel):
    """One stored cumulative snapshot per run, never a provider invoice."""

    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    source_user_id: UUID
    checkpoint_id: str = Field(min_length=1, max_length=100)
    recorded_at: datetime
    prompt_tokens: int = Field(ge=0, strict=True)
    completion_tokens: int = Field(ge=0, strict=True)
    stored_cost_usd: Decimal | None = Field(ge=0)
    estimated_cost_usd: Decimal | None = Field(ge=0)
    cost_state: Literal["recorded_estimate", "unrecorded", "allowance_possible"]


class CheckpointUsageSummary(BaseModel):
    """Anonymous recovered counts plus amounts that can be added without overlap."""

    model_config = ConfigDict(extra="forbid")
    runs: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    estimated_cost_usd: Decimal | None = Field(ge=0)
    unpriced_runs: int = Field(ge=0)
    overlapping_ledger_runs: int = Field(ge=0)
    additional_prompt_tokens: int = Field(ge=0)
    additional_completion_tokens: int = Field(ge=0)
    additional_estimated_cost_usd: Decimal | None = Field(ge=0)
    first_recorded_at: datetime | None
    last_recorded_at: datetime | None


def recover_usage_candidate(
    runtime: Mapping[str, object],
    values: Mapping[str, object],
    *,
    checkpoint_id: str,
    recorded_at: datetime,
) -> CheckpointUsageRun | None:
    """Validate counters and screen possible allowances without guessing model rates."""
    raw_cost = values.get("cost_usd")
    cost = None
    if raw_cost is not None and not isinstance(raw_cost, bool):
        try:
            parsed = Decimal(str(raw_cost))
            if parsed.is_finite() and parsed >= 0:
                cost = parsed
        except InvalidOperation:
            pass
    # A single unknown embedding attempt can add the smallest allowance to a
    # cumulative total. Without operation provenance, such totals stay unresolved.
    state = (
        "unrecorded"
        if cost is None
        else "allowance_possible"
        if cost >= min(USAGE_KIND_USD_CAPS.values())
        else "recorded_estimate"
    )
    try:
        return CheckpointUsageRun.model_validate(
            {
                "run_id": runtime.get("run_id"),
                "source_user_id": runtime.get("user_id"),
                "checkpoint_id": checkpoint_id,
                "recorded_at": recorded_at,
                "prompt_tokens": values.get("prompt_tokens"),
                "completion_tokens": values.get("completion_tokens"),
                "stored_cost_usd": cost,
                "estimated_cost_usd": cost if state == "recorded_estimate" else None,
                "cost_state": state,
            }
        )
    except ValidationError:
        return None


def deduplicate_checkpoint_usage(
    snapshots: Iterable[CheckpointUsageRun],
) -> tuple[CheckpointUsageRun, ...]:
    """Choose one latest nonzero cumulative snapshot per run; never sum snapshots."""
    runs: dict[UUID, CheckpointUsageRun] = {}

    def priority(row: CheckpointUsageRun) -> tuple[bool, datetime, str]:
        """Prefer measured usage, then the latest deterministic checkpoint."""
        return (
            row.prompt_tokens + row.completion_tokens > 0,
            row.recorded_at,
            row.checkpoint_id,
        )

    for row in snapshots:
        previous = runs.get(row.run_id)
        if previous is None or priority(row) > priority(previous):
            runs[row.run_id] = row
    return tuple(runs.values())


def combined_usage_cost(
    ledger_cost: Decimal | None,
    history: CheckpointUsageSummary | None,
    *,
    ledger_operations: int = 0,
) -> Decimal | None:
    """Add only checkpoint costs for runs absent from the application ledger."""
    recovered = history.additional_estimated_cost_usd if history else None
    if (
        ledger_cost == 0
        and ledger_operations == 0
        and history is not None
        and history.runs > history.overlapping_ledger_runs
        and recovered is None
    ):
        return None
    if ledger_cost is None and recovered is None:
        return None
    return (ledger_cost or Decimal(0)) + (recovered or Decimal(0))
