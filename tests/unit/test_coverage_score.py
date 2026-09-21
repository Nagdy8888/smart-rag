"""Coverage term matching, source-selector exclusion, and frozen threshold."""

from __future__ import annotations

from uuid import uuid4

import pytest
from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.retrieval.coverage import (
    CoverageDecision,
    CoverageSignal,
    HybridCoverage,
)
from smart_rag_core.retrieval.coverage_score import (
    attach_numeric_coverage,
    coverage_term_key,
    exclude_source_selector_terms,
)
from smart_rag_core.retrieval.frozen_profile import (
    COVERAGE_SCORE_BASELINE,
    coverage_threshold_for,
)
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


def _candidate() -> RetrievalCandidate:
    """Build one authorized fused candidate.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def test_source_selector_terms_are_not_required_answer_facts() -> None:
    """Naming a document cannot force a coverage refusal."""

    required = ("Policy Handbook", "retention")
    kept = exclude_source_selector_terms(required, ("Policy Handbook",))
    assert kept == ("retention",)
    fused = (_candidate(),)
    coverage = attach_numeric_coverage(
        HybridCoverage(signal=CoverageSignal.NONE),
        fused=fused,
        channel_hits={fused[0].chunk_id: frozenset({"dense", "term"})},
        query_type=QueryType.FACTUAL,
        required_terms=("Policy Handbook", "retention"),
        matched_terms=("retention",),
        source_selectors=("Policy Handbook",),
        rerank_top_support=0.9,
    )
    assert coverage.term_coverage == pytest.approx(1.0)
    assert coverage.decision is CoverageDecision.ANSWER
    assert coverage.threshold == pytest.approx(0.65)


def test_coverage_term_matching_uses_retrieval_normalization() -> None:
    """Coverage keys share ``arabic_norm_v1`` with candidate generation."""

    raw = "سياسة"
    assert coverage_term_key(raw) == normalize_arabic_v1(raw).casefold()
    fused = (_candidate(),)
    coverage = attach_numeric_coverage(
        HybridCoverage(signal=CoverageSignal.NONE),
        fused=fused,
        channel_hits={fused[0].chunk_id: frozenset({"dense", "term"})},
        required_terms=(raw,),
        matched_terms=(normalize_arabic_v1(raw),),
        rerank_top_support=0.9,
    )
    assert coverage.term_coverage == pytest.approx(1.0)


def test_frozen_coverage_threshold_stays_at_baseline() -> None:
    """P06-63 does not retune the 0.65 refuse threshold."""

    assert COVERAGE_SCORE_BASELINE == pytest.approx(0.65)
    assert coverage_threshold_for(None) == pytest.approx(0.65)
