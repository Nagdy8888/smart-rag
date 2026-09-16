"""Usage-kind caps and remaining-counter assertions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from smart_rag_core.query_admission.exceptions import QueryCeilingError

USAGE_KIND_USD_CAPS: dict[str, Decimal] = {
    "profile": Decimal("0.08"),
    "rewrite": Decimal("0.08"),
    "embedding": Decimal("0.02"),
    "lightrag": Decimal("0.25"),
    "rerank": Decimal("0.20"),
    "answer": Decimal("0.40"),
    "summary": Decimal("0.25"),
    "verifier": Decimal("0.20"),
}

USAGE_KIND_PROMPT_TOKEN_CAPS: dict[str, int] = {
    "profile": 4000,
    "rewrite": 4000,
    "embedding": 8000,
    "lightrag": 8000,
    "rerank": 12000,
    "answer": 8000,
    "summary": 6000,
    "verifier": 4000,
}

USAGE_KIND_COMPLETION_TOKEN_CAPS: dict[str, int] = {
    "profile": 1500,
    "rewrite": 1500,
    "embedding": 0,
    "lightrag": 2000,
    "rerank": 2000,
    "answer": 2000,
    "summary": 1500,
    "verifier": 1000,
}

ALLOWED_USAGE_KINDS: frozenset[str] = frozenset(USAGE_KIND_USD_CAPS)

ANSWER_STAGE_RESERVED_MODEL_CALLS = 2
"""One company answer call plus one verifier call. Does not raise ceilings."""

ANSWER_STAGE_MIN_SECONDS = 8.0
"""Minimum remaining wall time before a company answer provider call starts."""


def usage_kind_caps(usage_kind: str) -> tuple[Decimal, int, int]:
    """Return conservative per-call USD and token caps for one usage kind.

    Args:
        usage_kind: One of the allow-listed ``llm_usage.usage_kind`` values.

    Returns:
        ``(usd_cap, prompt_token_cap, completion_token_cap)``.

    Raises:
        QueryCeilingError: If the kind is not allow-listed.
    """

    if usage_kind not in ALLOWED_USAGE_KINDS:
        raise QueryCeilingError("unknown_usage_kind")
    return (
        USAGE_KIND_USD_CAPS[usage_kind],
        USAGE_KIND_PROMPT_TOKEN_CAPS[usage_kind],
        USAGE_KIND_COMPLETION_TOKEN_CAPS[usage_kind],
    )


def assert_deadline_open(*, now: datetime, deadline_at: datetime) -> None:
    """Refuse further work after the run deadline.

    Args:
        now: Current UTC timestamp.
        deadline_at: Server-assigned run deadline.

    Raises:
        QueryCeilingError: When ``now`` is at or after ``deadline_at``.
    """

    if now >= deadline_at:
        raise QueryCeilingError("deadline_exhausted")


def _assert_remaining(remaining: int, *, reason: str) -> int:
    """Decrement a remaining counter or fail closed.

    Args:
        remaining: Current remaining units.
        reason: Reason code when the counter is exhausted.

    Returns:
        ``remaining - 1``.

    Raises:
        QueryCeilingError: When ``remaining`` is already ``0`` or negative.
    """

    if remaining <= 0:
        raise QueryCeilingError(reason)
    return remaining - 1


def assert_optional_call_preserves_answer_reserve(remaining_model_calls: int) -> None:
    """Refuse optional spends that would consume the company answer reserve.

    Canonical Hybrid retrieval still runs; callers skip only the optional
    profile, correction, embed, or rerank spend when this fails.

    Args:
        remaining_model_calls: Remaining counted gateway calls before the spend.

    Raises:
        QueryCeilingError: When spending one call would leave fewer than
            ``ANSWER_STAGE_RESERVED_MODEL_CALLS``.
    """

    if remaining_model_calls - 1 < ANSWER_STAGE_RESERVED_MODEL_CALLS:
        raise QueryCeilingError("answer_stage_reserve_exhausted")


def assert_call_available(remaining_model_calls: int) -> int:
    """Consume one gateway model call from the remaining ceiling.

    Hybrid's seventh call is reserved for a correction rerank or a
    non-deferrable summary. Later packets enforce that policy; this helper
    only enforces the numeric ceiling.

    Args:
        remaining_model_calls: Remaining counted gateway calls.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the model-call ceiling is exhausted.
    """

    return _assert_remaining(remaining_model_calls, reason="model_call_exhausted")


def assert_tool_available(remaining_tool_calls: int) -> int:
    """Consume one tool execution from the remaining ceiling.

    Args:
        remaining_tool_calls: Remaining tool executions.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the tool ceiling is exhausted.
    """

    return _assert_remaining(remaining_tool_calls, reason="tool_exhausted")


def assert_discovery_available(remaining_discovery_rounds: int) -> int:
    """Consume the single optional discovery round.

    Args:
        remaining_discovery_rounds: Remaining discovery rounds.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When discovery is already used.
    """

    return _assert_remaining(remaining_discovery_rounds, reason="discovery_exhausted")


def assert_manifest_available(remaining_manifests: int) -> int:
    """Consume one optional tool manifest slot.

    Args:
        remaining_manifests: Remaining optional manifests.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the manifest ceiling is exhausted.
    """

    return _assert_remaining(remaining_manifests, reason="manifest_exhausted")


def assert_side_effect_available(remaining_side_effects: int) -> int:
    """Consume the single side-effecting tool slot.

    Args:
        remaining_side_effects: Remaining side-effecting tool slots.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When a side-effecting tool was already used.
    """

    return _assert_remaining(remaining_side_effects, reason="side_effect_exhausted")


def assert_recursion_available(remaining_recursion_steps: int) -> int:
    """Consume one LangGraph superstep from ``recursion_limit``.

    Args:
        remaining_recursion_steps: Remaining supersteps.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When recursion is exhausted.
    """

    return _assert_remaining(remaining_recursion_steps, reason="recursion_exhausted")


def assert_correction_available(remaining_corrections: int) -> int:
    """Consume the single routing/retrieval correction.

    Args:
        remaining_corrections: Remaining corrections.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the correction was already used.
    """

    return _assert_remaining(remaining_corrections, reason="correction_exhausted")


def assert_subquestion_available(remaining_subquestions: int) -> int:
    """Consume one subquestion slot.

    Args:
        remaining_subquestions: Remaining subquestions.

    Returns:
        Decremented remaining count.

    Raises:
        QueryCeilingError: When the subquestion ceiling is exhausted.
    """

    return _assert_remaining(remaining_subquestions, reason="subquestion_exhausted")
