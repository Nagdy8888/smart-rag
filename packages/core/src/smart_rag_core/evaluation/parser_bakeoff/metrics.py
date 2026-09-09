"""Paired bake-off metrics, bootstrap intervals, and classification."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
)
from smart_rag_core.evaluation.parser_bakeoff.models import (
    ChunkSummary,
    Classification,
    ComparisonReport,
    LaneAgentScore,
    LaneIdentity,
    LaneRetrieveScore,
    PairedMetric,
)
from smart_rag_core.evaluation.ranked_ids import recall_hit_at_k

Winner = Literal["current", "anydoc_local", "tie", "unavailable"]


def reciprocal_rank(ranked_ids: Sequence[UUID], gold_ids: Sequence[UUID]) -> float | None:
    """Return the reciprocal rank of the first gold chunk.

    Args:
        ranked_ids: Final ranked ids.
        gold_ids: Gold chunk ids.

    Returns:
        Reciprocal rank or ``None`` when gold is empty.
    """

    if not gold_ids:
        return None
    gold = set(gold_ids)
    for index, item in enumerate(ranked_ids, start=1):
        if item in gold:
            return 1.0 / float(index)
    return 0.0


def mean_optional(values: Sequence[float | None]) -> float | None:
    """Return the mean of non-null values.

    Args:
        values: Optional floats.

    Returns:
        Mean or ``None``.
    """

    present = tuple(item for item in values if item is not None)
    if not present:
        return None
    return sum(present) / len(present)


def mean_bools(values: Sequence[bool | None]) -> float | None:
    """Return the mean of boolean hits, ignoring ``None``.

    Args:
        values: Optional booleans.

    Returns:
        Mean in ``[0, 1]`` or ``None``.
    """

    present = tuple(item for item in values if item is not None)
    if not present:
        return None
    return sum(1.0 if item else 0.0 for item in present) / len(present)


def paired_delta(current: float | None, other: float | None) -> float | None:
    """Return ``other - current`` when both values exist.

    Args:
        current: Current-lane metric.
        other: AnyDoc-lane metric.

    Returns:
        Signed delta or ``None``.
    """

    if current is None or other is None:
        return None
    return other - current


def bootstrap_mean_ci(
    paired: Sequence[tuple[float, float]],
    *,
    seed: int = BOOTSTRAP_SEED,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> tuple[float | None, float | None]:
    """Return a 95% bootstrap CI for the mean paired delta.

    Args:
        paired: ``(current, anydoc)`` observations.
        seed: Recorded RNG seed.
        resamples: Bootstrap iterations.

    Returns:
        ``(ci_low, ci_high)`` or ``(None, None)`` when empty.
    """

    if not paired:
        return None, None
    rng = random.Random(seed)
    deltas = [right - left for left, right in paired]
    samples: list[float] = []
    count = len(deltas)
    for _ in range(resamples):
        draw = [deltas[rng.randrange(count)] for _ in range(count)]
        samples.append(sum(draw) / count)
    samples.sort()
    low_index = int(0.025 * (len(samples) - 1))
    high_index = int(0.975 * (len(samples) - 1))
    return samples[low_index], samples[high_index]


def metric_winner(
    current: float | None, other: float | None, *, higher_is_better: bool = True
) -> Winner:
    """Return a dimension winner without inventing missing values.

    Args:
        current: Current-lane value.
        other: AnyDoc value.
        higher_is_better: Direction.

    Returns:
        Winner token.
    """

    if current is None or other is None:
        return "unavailable"
    if abs(current - other) < 1e-12:
        return "tie"
    if higher_is_better:
        return "anydoc_local" if other > current else "current"
    return "anydoc_local" if other < current else "current"


def build_paired_metric(
    name: str,
    current: float | None,
    other: float | None,
    *,
    paired: Sequence[tuple[float, float]] = (),
    seed: int = BOOTSTRAP_SEED,
    higher_is_better: bool = True,
) -> PairedMetric:
    """Assemble one paired metric row.

    Args:
        name: Metric name.
        current: Current-lane aggregate.
        other: AnyDoc aggregate.
        paired: Optional per-case pairs for the CI.
        seed: Bootstrap seed.
        higher_is_better: Direction.

    Returns:
        Paired metric.
    """

    low, high = bootstrap_mean_ci(paired, seed=seed) if paired else (None, None)
    return PairedMetric(
        name=name,
        current=current,
        anydoc_local=other,
        delta=paired_delta(current, other),
        ci_low=low,
        ci_high=high,
        winner=metric_winner(current, other, higher_is_better=higher_is_better),
    )


def classify(
    *,
    recall: PairedMetric,
    faithfulness: PairedMetric,
    current_locator_available: bool,
    anydoc_locator_available: bool,
    acl_leaks: int,
    unscored_count: int,
    mapping_review_unresolved: int,
    infra_mismatch: bool,
) -> tuple[Classification, tuple[str, ...]]:
    """Apply the documented classification rule.

    Args:
        recall: Paired Recall@10.
        faithfulness: Paired faithfulness.
        current_locator_available: Current-lane page locators exist.
        anydoc_locator_available: AnyDoc page locators exist.
        acl_leaks: Cross-lane or ACL leak count.
        unscored_count: Unscored judge/mapping cases.
        mapping_review_unresolved: Remaining review items.
        infra_mismatch: True when settings hashes differ.

    Returns:
        Classification and reasons.
    """

    reasons: list[str] = []
    if acl_leaks:
        reasons.append("acl_or_cross_lane_leaks")
        return Classification.INCONCLUSIVE, tuple(reasons)
    if infra_mismatch:
        reasons.append("infrastructure_mismatch")
        return Classification.INCONCLUSIVE, tuple(reasons)
    if mapping_review_unresolved:
        reasons.append("gold_review_incomplete")
        return Classification.INCONCLUSIVE, tuple(reasons)
    if unscored_count:
        reasons.append("judge_or_cases_unscored")
        return Classification.INCONCLUSIVE, tuple(reasons)
    if (
        recall.ci_low is not None
        and recall.ci_high is not None
        and recall.ci_low <= 0.0 <= recall.ci_high
    ):
        reasons.append("recall_confidence_interval_crosses_zero")
        return Classification.INCONCLUSIVE, tuple(reasons)
    improved = (recall.delta or 0.0) > 0.0 and (faithfulness.delta or 0.0) >= 0.0
    if improved and anydoc_locator_available and current_locator_available:
        reasons.append("anydoc_improved_accuracy_with_locators")
        return Classification.ANYDOC_PRIMARY_CANDIDATE, tuple(reasons)
    if improved and not anydoc_locator_available:
        reasons.append("anydoc_improved_accuracy_without_pdf_locators")
        return Classification.ANYDOC_SECONDARY_CANDIDATE, tuple(reasons)
    reasons.append("current_retains_required_provenance_or_accuracy")
    return Classification.CURRENT_PRIMARY, tuple(reasons)


def compare_reports(
    *,
    run_id: str,
    source_sha256: str,
    source_basename: str,
    current_identity: LaneIdentity,
    anydoc_identity: LaneIdentity,
    current_chunk: ChunkSummary | None,
    anydoc_chunk: ChunkSummary | None,
    current_retrieve: tuple[LaneRetrieveScore, ...],
    anydoc_retrieve: tuple[LaneRetrieveScore, ...],
    current_agent: tuple[LaneAgentScore, ...],
    anydoc_agent: tuple[LaneAgentScore, ...],
    mapping_review_count: int,
    infra_mismatch: bool,
    blockers: tuple[str, ...] = (),
) -> ComparisonReport:
    """Build the side-by-side comparison report.

    Args:
        run_id: Run identifier.
        source_sha256: PDF hash.
        source_basename: PDF basename.
        current_identity: Current lane identity.
        anydoc_identity: AnyDoc lane identity.
        current_chunk: Optional current summary.
        anydoc_chunk: Optional AnyDoc summary.
        current_retrieve: Current retrieval scores.
        anydoc_retrieve: AnyDoc retrieval scores.
        current_agent: Current answer scores.
        anydoc_agent: AnyDoc answer scores.
        mapping_review_count: Remaining review items.
        infra_mismatch: Settings mismatch flag.
        blockers: Sanitized blocker codes.

    Returns:
        Frozen comparison report.
    """

    current_recall = mean_bools(tuple(item.recall_hit_at_10 for item in current_retrieve))
    anydoc_recall = mean_bools(tuple(item.recall_hit_at_10 for item in anydoc_retrieve))
    recall_pairs = tuple(
        (1.0 if left.recall_hit_at_10 else 0.0, 1.0 if right.recall_hit_at_10 else 0.0)
        for left, right in zip(current_retrieve, anydoc_retrieve, strict=False)
        if left.recall_hit_at_10 is not None and right.recall_hit_at_10 is not None
    )
    recall_metric = build_paired_metric(
        "hybrid_recall_at_10", current_recall, anydoc_recall, paired=recall_pairs
    )
    current_cit = mean_optional(tuple(item.citation_correctness for item in current_agent))
    anydoc_cit = mean_optional(tuple(item.citation_correctness for item in anydoc_agent))
    citation_metric = build_paired_metric(
        "citation_correctness", current_cit, anydoc_cit
    )
    current_faith = mean_optional(tuple(item.faithfulness for item in current_agent))
    anydoc_faith = mean_optional(tuple(item.faithfulness for item in anydoc_agent))
    faith_pairs = tuple(
        (left.faithfulness, right.faithfulness)
        for left, right in zip(current_agent, anydoc_agent, strict=False)
        if left.faithfulness is not None and right.faithfulness is not None
    )
    faith_metric = build_paired_metric(
        "judge_faithfulness", current_faith, anydoc_faith, paired=faith_pairs
    )
    current_locator = mean_bools(tuple(item.locator_ok for item in current_retrieve))
    anydoc_locator = (
        0.0
        if anydoc_retrieve and not anydoc_identity.locator_available
        else mean_bools(tuple(item.locator_ok for item in anydoc_retrieve))
    )
    locator_metric = build_paired_metric(
        "locator_correctness", current_locator, anydoc_locator
    )
    current_lat = mean_optional(
        tuple(item.first_evidence_ms for item in current_retrieve)
    )
    anydoc_lat = mean_optional(
        tuple(item.first_evidence_ms for item in anydoc_retrieve)
    )
    latency_metric = build_paired_metric(
        "first_evidence_ms",
        current_lat,
        anydoc_lat,
        higher_is_better=False,
    )
    acl_leaks = sum(
        item.cross_lane_leaks + int(item.acl_leak)
        for item in (*current_retrieve, *anydoc_retrieve)
    )
    unscored = sum(1 for item in (*current_agent, *anydoc_agent) if item.judge_status != "complete")
    classification, reasons = classify(
        recall=recall_metric,
        faithfulness=faith_metric,
        current_locator_available=current_identity.locator_available,
        anydoc_locator_available=anydoc_identity.locator_available,
        acl_leaks=acl_leaks,
        unscored_count=unscored,
        mapping_review_unresolved=mapping_review_count,
        infra_mismatch=infra_mismatch,
    )
    current_cost = mean_optional(tuple(item.cost_usd for item in current_agent))
    anydoc_cost = mean_optional(tuple(item.cost_usd for item in anydoc_agent))
    return ComparisonReport(
        run_id=run_id,
        source_sha256=source_sha256,
        source_basename=source_basename,
        current=current_identity,
        anydoc_local=anydoc_identity,
        current_chunk=current_chunk,
        anydoc_chunk=anydoc_chunk,
        paired_metrics=(
            recall_metric,
            citation_metric,
            faith_metric,
            locator_metric,
            latency_metric,
        ),
        classification=classification,
        classification_reasons=reasons,
        blockers=blockers,
        unscored_count=unscored,
        mapping_review_count=mapping_review_count,
        acl_leaks=acl_leaks,
        current_cost_usd=current_cost,
        anydoc_cost_usd=anydoc_cost,
        bootstrap_seed=BOOTSTRAP_SEED,
    )


def recall_hit(ranked_ids: Sequence[UUID], gold_ids: Sequence[UUID], k: int) -> bool:
    """Proxy ``recall_hit_at_k`` for bake-off callers.

    Args:
        ranked_ids: Ranked evidence ids.
        gold_ids: Gold ids.
        k: Cutoff.

    Returns:
        Hit flag.
    """

    return recall_hit_at_k(ranked_ids, gold_ids, k)
