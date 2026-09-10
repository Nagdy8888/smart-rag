"""Contract tests for version-scoped bake-off retrieval isolation."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from smart_rag_core.evaluation.parser_bakeoff.evaluate import (
    alternate_lane_order,
    assert_version_scoped,
)
from smart_rag_core.evaluation.parser_bakeoff.models import BakeoffError
from smart_rag_core.retrieval.coverage import (
    CoverageDecision,
    CoverageSignal,
    HybridCoverage,
)
from smart_rag_core.retrieval.hybrid_run.types import (
    EvidenceLocator,
    EvidenceUnit,
    HybridRunResult,
)
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason


def _result(
    *,
    ranked: tuple[UUID, ...],
    evidence: tuple[EvidenceUnit, ...],
) -> HybridRunResult:
    """Build a Hybrid result for scope checks.

    Args:
        ranked: Ranked chunk ids.
        evidence: Evidence units.

    Returns:
        Hybrid run result.
    """

    return HybridRunResult(
        ranked_ids=ranked,
        evidence=evidence,
        coverage=HybridCoverage(
            signal=CoverageSignal.NONE,
            decision=CoverageDecision.ANSWER,
        ),
        fallback_reason=RetrievalFallbackReason.NONE,
        deadline_exhausted=False,
        first_evidence_ms=11.0,
        embedding_call_count=1,
        rerank_call_count=1,
    )


def test_restrict_version_id_rejects_cross_lane_ids() -> None:
    """A foreign ranked or evidence id hard-fails with a leak code."""

    current_version = uuid4()
    current_chunk = uuid4()
    foreign_chunk = uuid4()
    ok = _result(
        ranked=(current_chunk,),
        evidence=(
            EvidenceUnit(
                chunk_id=current_chunk,
                document_id=uuid4(),
                version_id=current_version,
                citation_text="authorized",
                locator=EvidenceLocator(page_number=3),
            ),
        ),
    )
    assert (
        assert_version_scoped(
            ok,
            allowed_chunk_ids=frozenset({current_chunk}),
            version_id=current_version,
            foreign_chunk_ids=frozenset({foreign_chunk}),
        )
        == 0
    )
    leaked = _result(
        ranked=(foreign_chunk,),
        evidence=(),
    )
    with pytest.raises(BakeoffError) as err:
        assert_version_scoped(
            leaked,
            allowed_chunk_ids=frozenset({current_chunk}),
            version_id=current_version,
            foreign_chunk_ids=frozenset({foreign_chunk}),
        )
    assert err.value.code == "cross_lane_id"


def test_evidence_version_mismatch_fails_closed() -> None:
    """Evidence must belong to the lane version."""

    version = uuid4()
    other = uuid4()
    chunk = uuid4()
    mismatched = _result(
        ranked=(chunk,),
        evidence=(
            EvidenceUnit(
                chunk_id=chunk,
                document_id=uuid4(),
                version_id=other,
                citation_text="wrong version",
                locator=EvidenceLocator(),
            ),
        ),
    )
    with pytest.raises(BakeoffError) as err:
        assert_version_scoped(
            mismatched,
            allowed_chunk_ids=frozenset({chunk}),
            version_id=version,
            foreign_chunk_ids=frozenset(),
        )
    assert err.value.code == "version_scope"


def test_alternate_lane_order_is_sequential() -> None:
    """Paired eval alternates starting lane without parallel execution."""

    assert alternate_lane_order(0) == ("current", "anydoc_local")
    assert alternate_lane_order(1) == ("anydoc_local", "current")
