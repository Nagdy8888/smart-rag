"""Promotion gates for general Hybrid retrieval accuracy.

These gates are independent of any one sample PDF. They refuse promotion on
strict score alone, refuse holdout opening, and refuse a generalization
claim without disjoint real documents.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

MIN_GROUNDED_FACT_RATE = 0.95
"""Minimum grounded required-fact rate on the development sample."""

MIN_DISJOINT_REAL_DOCUMENTS = 2
"""Minimum distinct real documents before generalization may be claimed."""


class AccuracyPromotionError(ValueError):
    """Raised when a promotion decision would violate a negative test."""


@dataclass(frozen=True, slots=True)
class AccuracyPromotionDecision:
    """Redacted promotion outcome for one qualification packet.

    Attributes:
        sample_promoted: True when sample grounded-fact and operational
            gates pass.
        generalization_claimed: True only with disjoint real documents.
        reasons: Machine-readable refusal or pass tokens.
        grounded_fact_rate: Reported grounded required-fact rate.
        strict_rate: Reported strict phrase rate. Never sufficient alone.
        deadline_failures: Product deadline failures on the sample.
        holdout_opened: Must stay false.
        unknown_required_fields: Count of required promotion inputs that
            were not measured.
    """

    sample_promoted: bool
    generalization_claimed: bool
    reasons: tuple[str, ...]
    grounded_fact_rate: float
    strict_rate: float
    deadline_failures: int
    holdout_opened: bool
    unknown_required_fields: int


def decide_accuracy_promotion(
    summary: Mapping[str, float | int],
    *,
    acl_leaks: int,
    bm25_degraded_explicit: bool,
    holdout_opened: bool,
    disjoint_real_document_count: int,
    sample_gold_in_production: bool,
    rerank_accounting_ok: bool,
    unknown_required_fields: int = 0,
) -> AccuracyPromotionDecision:
    """Decide whether the sample may be promoted and generalization claimed.

    Args:
        summary: Dual-metric aggregate from :func:`summarize_scores`.
        acl_leaks: Unauthorized documents that entered results.
        bm25_degraded_explicit: True when BM25 outage is a named degradation.
        holdout_opened: Holdout custody flag. Must stay false.
        disjoint_real_document_count: Distinct real documents besides the
            development sample.
        sample_gold_in_production: True when sample gold is embedded in
            production modules.
        rerank_accounting_ok: Durable retrieve accounting and rerank reserve
            gates passed.
        unknown_required_fields: Count of required measured fields that are
            missing. Any positive count blocks promotion.

    Returns:
        Promotion decision. Generalization stays unverified without disjoint
        real documents.

    Raises:
        AccuracyPromotionError: Holdout opened, sample gold hardcoded, or
            promotion attempted from strict score alone.
    """

    if holdout_opened:
        raise AccuracyPromotionError("holdout_opened")
    if sample_gold_in_production:
        raise AccuracyPromotionError("sample_gold_in_production")
    questions = int(summary.get("questions", 0) or 0)
    grounded = float(summary.get("grounded_fact_rate", 0.0) or 0.0)
    strict = float(summary.get("strict_rate", 0.0) or 0.0)
    deadlines = int(summary.get("deadline_failures", 0) or 0)
    reasons: list[str] = []
    if questions <= 0:
        reasons.append("no_questions")
    if grounded < MIN_GROUNDED_FACT_RATE:
        reasons.append("grounded_fact_below_95")
    if deadlines != 0:
        reasons.append("deadline_failures")
    if acl_leaks != 0:
        reasons.append("acl_leaks")
    if not bm25_degraded_explicit:
        reasons.append("bm25_degradation_not_explicit")
    if not rerank_accounting_ok:
        reasons.append("rerank_accounting_unproven")
    if unknown_required_fields > 0:
        reasons.append("unknown_required_fields")
    if strict >= MIN_GROUNDED_FACT_RATE and grounded < MIN_GROUNDED_FACT_RATE:
        raise AccuracyPromotionError("strict_score_alone")
    sample_promoted = not reasons
    generalization = (
        sample_promoted and disjoint_real_document_count >= MIN_DISJOINT_REAL_DOCUMENTS
    )
    if not generalization:
        reasons.append("generalization_unverified")
    return AccuracyPromotionDecision(
        sample_promoted=sample_promoted,
        generalization_claimed=generalization,
        reasons=tuple(reasons),
        grounded_fact_rate=grounded,
        strict_rate=strict,
        deadline_failures=deadlines,
        holdout_opened=False,
        unknown_required_fields=unknown_required_fields,
    )
