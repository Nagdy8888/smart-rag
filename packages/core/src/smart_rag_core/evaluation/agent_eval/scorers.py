"""Deterministic agent-eval scorers and summary helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import cast

from smart_rag_core.evaluation.agent_eval.schema import (
    REFUSAL_ROUTE_ALIASES,
    AgentEvalOutput,
    AgentEvalReference,
)
from smart_rag_core.evaluation.schema import (
    ExpectedRoute,
    RefusalKind,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def score_route_correct(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score whether the effective route matches the labeled route.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        ``1.0`` on an allowed mapping, otherwise ``0.0``.
    """

    effective = (output.effective_route or "").strip().lower()
    expected = reference.expected_route.strip().lower()
    if expected == ExpectedRoute.REFUSAL.value:
        return 1.0 if effective in REFUSAL_ROUTE_ALIASES else 0.0
    return 1.0 if effective == expected else 0.0


def score_refusal_correct(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score refusal/limitation behavior against labeled truth.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        ``1.0`` when refusal or answer behavior matches the label.
    """

    expected_refusal = reference.refusal_kind != RefusalKind.NONE.value
    status = output.answer_status
    refused_or_limited = status in {"refused", "partial"}
    complete_answer = status == "complete"
    if expected_refusal:
        return 1.0 if refused_or_limited else 0.0
    if complete_answer:
        return 1.0
    return 0.0


def score_citation_precision(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score citation precision against visible gold ids.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Precision in ``[0, 1]``. Empty/empty is ``1.0``. Citations with no
        visible gold score ``0.0``.
    """

    cited = _cited_ids(output)
    gold = _visible_gold_ids(reference)
    if not cited and not gold:
        return 1.0
    if cited and not gold:
        return 0.0
    if not cited:
        return 0.0
    return len(cited & gold) / len(cited)


def score_citation_recall(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score citation recall against visible gold ids.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Recall in ``[0, 1]``. Empty/empty is ``1.0``.
    """

    cited = _cited_ids(output)
    gold = _visible_gold_ids(reference)
    if not cited and not gold:
        return 1.0
    if not gold:
        return 1.0 if not cited else 0.0
    return len(cited & gold) / len(gold)


def score_acl_leak_free(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Score whether cited or selected ids stay outside forbidden evidence.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        ``1.0`` only when no cited/selected id is forbidden or invisible.
    """

    used = _cited_ids(output) | set(output.selected_evidence_ids)
    forbidden = set(reference.forbidden_evidence_ids)
    if used & forbidden:
        return 0.0
    return 1.0


def score_profile_fields_correct(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> tuple[float, dict[str, float]]:
    """Compare structured preparation fields with the frozen expected profile.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Aggregate score in ``[0, 1]`` and per-field scores.
    """

    expected = reference.expected_profile_fields
    if not expected:
        return 1.0, {}
    observed = output.profile_fields
    per_field: dict[str, float] = {}
    for key, gold in expected.items():
        got = observed.get(key)
        per_field[key] = 1.0 if _values_equal(got, gold) else 0.0
    aggregate = sum(per_field.values()) / len(per_field)
    return aggregate, per_field


def score_bounds_respected(output: AgentEvalOutput) -> float:
    """Score whether deadline and remaining ceilings stayed non-negative.

    Args:
        output: Target output.

    Returns:
        ``1.0`` when all remaining counters are present and non-negative and
        the deadline was not exceeded. Infrastructure gaps score ``0.0``.
    """

    remaining = (
        output.remaining_model_calls,
        output.remaining_tool_calls,
        output.remaining_corrections,
        output.remaining_subquestions,
        output.remaining_recursion_steps,
    )
    if any(value is None for value in remaining):
        return 0.0
    if any(int(value or 0) < 0 for value in remaining):
        return 0.0
    if output.deadline_exceeded:
        return 0.0
    return 1.0


def score_answer_reference_overlap(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> float:
    """Diagnostic token overlap against acceptable answers. Not a release gate.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Overlap in ``[0, 1]``. Empty acceptable answers yield ``1.0`` when the
        agent also produced no answer text.
    """

    answer_tokens = _tokens(output.answer_text)
    gold_sets = [_tokens(item) for item in reference.acceptable_answers]
    if not gold_sets:
        return 1.0 if not answer_tokens else 0.0
    if not answer_tokens:
        return 0.0
    best = 0.0
    for gold in gold_sets:
        if not gold:
            continue
        overlap = len(answer_tokens & gold) / len(answer_tokens | gold)
        if overlap > best:
            best = overlap
    return best


def score_target_completed(output: AgentEvalOutput) -> float:
    """Score whether the target produced a valid terminal output.

    Args:
        output: Target output.

    Returns:
        ``1.0`` when completed, otherwise ``0.0``.
    """

    return 1.0 if output.completed else 0.0


def score_all(
    output: AgentEvalOutput, reference: AgentEvalReference
) -> dict[str, float]:
    """Return every deterministic evaluator score for one case.

    Args:
        output: Target output.
        reference: Frozen reference.

    Returns:
        Mapping of stable evaluator keys to numeric scores.
    """

    profile_score, _per_field = score_profile_fields_correct(output, reference)
    return {
        "route_correct": score_route_correct(output, reference),
        "refusal_correct": score_refusal_correct(output, reference),
        "citation_precision": score_citation_precision(output, reference),
        "citation_recall": score_citation_recall(output, reference),
        "acl_leak_free": score_acl_leak_free(output, reference),
        "profile_fields_correct": profile_score,
        "bounds_respected": score_bounds_respected(output),
        "answer_reference_overlap": score_answer_reference_overlap(output, reference),
        "target_completed": score_target_completed(output),
    }


def hard_failure_reasons(
    output: AgentEvalOutput, scores: Mapping[str, float]
) -> tuple[str, ...]:
    """Return hard-failure reasons that must not be averaged away.

    Args:
        output: Target output.
        scores: Deterministic scores.

    Returns:
        Ordered reason tokens. ACL leaks are always included when scored 0.
    """

    reasons: list[str] = []
    if scores.get("acl_leak_free", 1.0) == 0.0:
        reasons.append("acl_leak_free")
    if scores.get("target_completed", 1.0) == 0.0:
        reasons.append(output.failure_kind or "target_incomplete")
    return tuple(reasons)


def median_latency_ms(values: Sequence[int]) -> int | None:
    """Return the median of recorded latencies.

    Args:
        values: Latency samples in milliseconds.

    Returns:
        Median as an int, or None when empty.
    """

    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def decimal_sum(values: Sequence[str]) -> str:
    """Sum decimal strings without binary float rounding.

    Args:
        values: Decimal strings.

    Returns:
        Sum as a normalized decimal string.
    """

    total = sum((Decimal(item) for item in values), Decimal("0"))
    return format(total, "f")


def _cited_ids(output: AgentEvalOutput) -> set[str]:
    """Return cited chunk and table identifiers.

    Args:
        output: Target output.

    Returns:
        Set of cited ids.
    """

    return set(output.cited_chunk_ids) | set(output.cited_table_ids)


def _visible_gold_ids(reference: AgentEvalReference) -> set[str]:
    """Return visible gold chunk and table identifiers.

    Args:
        reference: Frozen reference.

    Returns:
        Set of visible gold ids.
    """

    return set(reference.visible_chunk_ids) | set(reference.visible_table_ids)


def _tokens(text: str) -> set[str]:
    """Return lowercase alphanumeric tokens for diagnostic overlap.

    Args:
        text: Answer or gold text.

    Returns:
        Token set.
    """

    return {item.lower() for item in _TOKEN_RE.findall(text)}


def _values_equal(left: object, right: object) -> bool:
    """Compare profile values with list/tuple normalization.

    Args:
        left: Observed value.
        right: Expected value.

    Returns:
        True when values are equal after sequence normalization.
    """

    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return tuple(cast(Sequence[object], left)) == tuple(
            cast(Sequence[object], right)
        )
    return left == right
