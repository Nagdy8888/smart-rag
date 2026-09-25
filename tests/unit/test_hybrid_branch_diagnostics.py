"""ID-only Hybrid branch diagnostics stay text-free and backward compatible."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branch_channels.hybrid import (
    hybrid_diagnostics_from_outcome,
)
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchResult,
    HybridBranchDiagnostics,
)
from smart_rag_core.retrieval.coverage import CoverageSignal, HybridCoverage
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID

from scripts.eval_ask_stage_export import stage_record
from scripts.run_company_ask import unknown_required_count

_FORBIDDEN_TEXT_FIELDS = frozenset(
    {
        "query",
        "query_text",
        "title",
        "snippet",
        "passage",
        "answer",
        "citation_text",
        "raw_text",
        "text",
    }
)


def _diagnostics(**overrides: object) -> HybridBranchDiagnostics:
    """Build a valid ID-only diagnostics fixture.

    Args:
        overrides: Field replacements.

    Returns:
        Frozen diagnostics.
    """

    payload: dict[str, object] = {
        "source_resolution": "exact_one",
        "retrieval_profile_id": HYBRID_DEFAULT_PROFILE_ID,
        "fallback_reason": "none",
        "rerank_fallback": "none",
        "rerank_call_count": 1,
        "embedding_call_count": 1,
        "first_evidence_ms": 12.5,
        "dense_ids": (str(uuid4()),),
        "bm25_ids": (str(uuid4()),),
        "term_ids": (str(uuid4()),),
        "fused_ids": (str(uuid4()),),
        "selected_ids": (str(uuid4()),),
        "effective_route": Phase6RouteFamily.HYBRID.value,
    }
    payload.update(overrides)
    return HybridBranchDiagnostics.model_validate(payload)


def test_hybrid_diagnostics_have_no_text_fields() -> None:
    """Diagnostics persist IDs and enumerated metadata only."""

    names = set(HybridBranchDiagnostics.model_fields)
    assert names.isdisjoint(_FORBIDDEN_TEXT_FIELDS)


def test_hybrid_diagnostics_reject_extra_text_field() -> None:
    """An undeclared passage field cannot be smuggled onto the model."""

    with pytest.raises(ValidationError):
        HybridBranchDiagnostics.model_validate(
            {
                **_diagnostics().model_dump(),
                "citation_text": "not-allowed",
            }
        )


def test_hybrid_diagnostics_enforce_id_caps() -> None:
    """Channel ID lists are bounded."""

    too_many = tuple(str(uuid4()) for _ in range(101))
    with pytest.raises(ValidationError):
        _diagnostics(dense_ids=too_many)
    with pytest.raises(ValidationError):
        _diagnostics(bm25_ids=tuple(str(uuid4()) for _ in range(76)))
    with pytest.raises(ValidationError):
        _diagnostics(term_ids=tuple(str(uuid4()) for _ in range(31)))
    with pytest.raises(ValidationError):
        _diagnostics(selected_ids=tuple(str(uuid4()) for _ in range(13)))
    with pytest.raises(ValidationError):
        _diagnostics(rerank_pool_ids=tuple(str(uuid4()) for _ in range(101)))


def test_hybrid_diagnostics_reject_non_uuid_ids() -> None:
    """A title or snippet cannot be stored as a channel ID."""

    with pytest.raises(ValidationError):
        _diagnostics(dense_ids=("not-a-uuid",))


def test_hybrid_diagnostics_serialization_is_deterministic() -> None:
    """JSON dumps of the same diagnostics are byte-identical."""

    pool_id = str(uuid4())
    row = _diagnostics(rerank_pool_ids=(pool_id,))
    first = row.model_dump_json()
    restored = HybridBranchDiagnostics.model_validate_json(first)
    second = restored.model_dump_json()
    assert first == second
    assert restored.rerank_pool_ids == (pool_id,)


def test_branch_result_without_diagnostics_still_validates() -> None:
    """Older checkpoints without hybrid_diagnostics remain valid."""

    result = BranchResult.model_validate(
        {
            "branch_id": "hybrid-1",
            "kind": BranchKind.HYBRID,
            "family": Phase6RouteFamily.HYBRID,
            "run_id": str(uuid4()),
            "reservation_id": str(uuid4()),
            "query_text": "generic question",
            "fallback_reason": "none",
        }
    )
    assert result.hybrid_diagnostics is None


def test_company_ask_runner_has_no_hardcoded_promotion_flags() -> None:
    """The Ask runner must not invent measured promotion inputs."""

    text = Path("scripts/run_company_ask.py").read_text(encoding="utf-8")
    assert "bm25_degraded_explicit=True" not in text
    assert "rerank_accounting_ok=True" not in text
    assert "SourceResolutionStage.UNSCOPED.value" not in text
    assert "fused_count = citation_count" not in text


def test_hybrid_diagnostics_from_none_fallback_persist() -> None:
    """Successful retrieve still stores fallback_reason=none."""

    chunk = str(uuid4())
    outcome = SimpleNamespace(
        source_resolution="exact_one",
        retrieval_profile_id=HYBRID_DEFAULT_PROFILE_ID,
        rerank_fallback="none",
        rerank_call_count=1,
        embedding_call_count=1,
        first_evidence_ms=8.0,
        dense_ids=(chunk,),
        bm25_ids=(chunk,),
        term_ids=(chunk,),
        fused_ids=(chunk,),
        selected_ids=(chunk,),
        rerank_order=(uuid4(), uuid4()),
        coverage=HybridCoverage(
            signal=CoverageSignal.NONE,
            coverage_score=0.8,
            term_coverage=1.0,
            subquestion_coverage=1.0,
            evidence_ratio=0.8,
            support_confidence=0.7,
        ),
    )
    row = hybrid_diagnostics_from_outcome(
        outcome,
        effective_route=Phase6RouteFamily.HYBRID.value,
        fallback_reason="none",
    )
    assert row is not None
    assert row.fallback_reason == "none"
    assert row.source_resolution == "exact_one"
    assert row.dense_ids == (chunk,)
    assert row.rerank_pool_ids == tuple(str(item) for item in outcome.rerank_order)


def test_hybrid_diagnostics_omit_when_source_resolution_missing() -> None:
    """Missing required tokens stay unknown instead of inventing values."""

    row = hybrid_diagnostics_from_outcome(
        SimpleNamespace(
            source_resolution="",
            retrieval_profile_id=HYBRID_DEFAULT_PROFILE_ID,
            rerank_fallback="none",
        ),
        effective_route=Phase6RouteFamily.HYBRID.value,
        fallback_reason="none",
    )
    assert row is None


def test_stage_record_measures_accounting_and_bm25_explicit() -> None:
    """Export flags come from diagnostics plus llm_usage, not defaults."""

    chunk = str(uuid4())
    diagnostics = {
        "source_resolution": "exact_one",
        "retrieval_profile_id": HYBRID_DEFAULT_PROFILE_ID,
        "fallback_reason": "none",
        "rerank_fallback": "none",
        "rerank_call_count": 1,
        "embedding_call_count": 1,
        "dense_ids": [chunk],
        "bm25_ids": [chunk],
        "term_ids": [chunk],
        "fused_ids": [chunk],
        "selected_ids": [chunk],
        "rerank_pool_ids": [chunk],
        "effective_route": "hybrid",
    }
    ok = stage_record(diagnostics, {"embedding", "rerank"})
    assert ok["rerank_accounting_ok"] is True
    assert ok["bm25_degraded_explicit"] is False
    assert ok["retrieval_empty"] is False
    assert ok["rerank_pool_ids"] == [chunk]
    masked = stage_record(
        {**diagnostics, "fallback_reason": "term_unavailable"},
        {"embedding", "rerank"},
    )
    assert masked["bm25_degraded_explicit"] is False
    named = stage_record(
        {**diagnostics, "fallback_reason": "bm25_unavailable"},
        {"embedding"},
    )
    assert named["bm25_degraded_explicit"] is True
    assert named["rerank_accounting_ok"] is False
    missing = stage_record(None, set())
    assert missing["source_resolution"] == "unknown"
    assert missing["rerank_accounting_ok"] == "unknown"
    assert missing["rerank_pool_ids"] == "unknown"


def test_unknown_required_count_keeps_measured_zero() -> None:
    """A measured zero must not be replaced with the question count."""

    assert unknown_required_count({"unknown_required_fields": 0}, 3) == 0
    assert unknown_required_count({}, 3) == 3
