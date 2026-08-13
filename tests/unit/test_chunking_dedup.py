"""Unit tests for duplicate detection policy."""

from __future__ import annotations

from smart_rag_core.ingestion.chunking.dedup import (
    DEFAULT_FUZZY_FIXTURES,
    evaluate_fuzzy_policy,
    measure_fuzzy_metrics,
)
from smart_rag_core.ingestion.chunking.limits import (
    NEAR_DUP_MIN_PRECISION,
    NEAR_DUP_MIN_RECALL,
)


def test_fuzzy_policy_meets_precision_recall_gate_or_exact_only() -> None:
    """Near-dup policy must meet gates or fall back to exact-only."""

    precision, recall = measure_fuzzy_metrics(DEFAULT_FUZZY_FIXTURES)
    enabled = evaluate_fuzzy_policy(DEFAULT_FUZZY_FIXTURES)
    if enabled:
        assert precision >= NEAR_DUP_MIN_PRECISION
        assert recall >= NEAR_DUP_MIN_RECALL
    else:
        assert precision < NEAR_DUP_MIN_PRECISION or recall < NEAR_DUP_MIN_RECALL
