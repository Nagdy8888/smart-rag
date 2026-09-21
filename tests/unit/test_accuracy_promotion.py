"""Promotion-gate negatives for Hybrid retrieval accuracy."""

from __future__ import annotations

import pytest
from smart_rag_core.evaluation.accuracy_promotion import (
    AccuracyPromotionError,
    decide_accuracy_promotion,
)


def _summary(
    *, grounded: float, strict: float, deadlines: int = 0
) -> dict[str, float | int]:
    """Build a dual-metric summary.

    Args:
        grounded: Grounded fact rate.
        strict: Strict phrase rate.
        deadlines: Deadline failures.

    Returns:
        Aggregate mapping.
    """

    return {
        "questions": 100,
        "grounded_fact_rate": grounded,
        "strict_rate": strict,
        "deadline_failures": deadlines,
    }


def test_strict_score_alone_cannot_promote() -> None:
    """A perfect lexical score without fact coverage is not promotion."""

    with pytest.raises(AccuracyPromotionError, match="strict_score_alone"):
        decide_accuracy_promotion(
            _summary(grounded=0.40, strict=0.96),
            acl_leaks=0,
            bm25_degraded_explicit=True,
            holdout_opened=False,
            disjoint_real_document_count=0,
            sample_gold_in_production=False,
            rerank_accounting_ok=True,
        )


def test_hardcoded_sample_gold_cannot_promote() -> None:
    """Embedding sample-PDF answers in production fails the gate."""

    with pytest.raises(AccuracyPromotionError, match="sample_gold_in_production"):
        decide_accuracy_promotion(
            _summary(grounded=1.0, strict=1.0),
            acl_leaks=0,
            bm25_degraded_explicit=True,
            holdout_opened=False,
            disjoint_real_document_count=3,
            sample_gold_in_production=True,
            rerank_accounting_ok=True,
        )


def test_opening_holdout_cannot_chase_the_gate() -> None:
    """Holdout stays sealed during accuracy remediation."""

    with pytest.raises(AccuracyPromotionError, match="holdout_opened"):
        decide_accuracy_promotion(
            _summary(grounded=0.99, strict=0.90),
            acl_leaks=0,
            bm25_degraded_explicit=True,
            holdout_opened=True,
            disjoint_real_document_count=3,
            sample_gold_in_production=False,
            rerank_accounting_ok=True,
        )


def test_generalization_unverified_without_disjoint_documents() -> None:
    """Sample promotion does not imply generalization."""

    decision = decide_accuracy_promotion(
        _summary(grounded=0.96, strict=0.80, deadlines=0),
        acl_leaks=0,
        bm25_degraded_explicit=True,
        holdout_opened=False,
        disjoint_real_document_count=0,
        sample_gold_in_production=False,
        rerank_accounting_ok=True,
    )
    assert decision.sample_promoted is True
    assert decision.generalization_claimed is False
    assert "generalization_unverified" in decision.reasons
    assert decision.holdout_opened is False
