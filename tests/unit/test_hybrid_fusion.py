"""Unit tests for Phase 4 Packet 4 RRF, temporal policy, and coverage."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from smart_rag_core.retrieval.cache_key import cache_payload, hybrid_cache_key
from smart_rag_core.retrieval.coverage import CoverageSignal
from smart_rag_core.retrieval.fusion import (
    FusionError,
    fuse_channels,
    rrf_contribution,
)
from smart_rag_core.retrieval.hybrid import assemble_hybrid, run_channels_parallel
from smart_rag_core.retrieval.profiles import (
    DENSE_CANDIDATE_CAP,
    PREFUSION_UNION_CAP,
    RRF_K,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.temporal import (
    TemporalDocument,
    TemporalIntent,
    apply_temporal_policy,
)
from smart_rag_core.retrieval.types import RetrievalCandidate


def _candidate(chunk: UUID | None = None, rank: int = 1) -> RetrievalCandidate:
    """Build one synthetic authorized candidate.

    Args:
        chunk: Optional chunk id.
        rank: Channel rank.

    Returns:
        Frozen candidate.
    """

    ident = chunk or uuid4()
    return RetrievalCandidate(
        chunk_id=ident,
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=rank,
        channel_score=1.0,
    )


def test_rrf_k_is_plan_fixed() -> None:
    """Packet 4 uses rrf_k=60 and rejects other smoothers."""

    assert RRF_K == 60
    assert rrf_contribution(1) == pytest.approx(1.0 / 61.0)
    with pytest.raises(FusionError, match="rrf_k_not_allowlisted"):
        rrf_contribution(1, k=59)


def test_rrf_is_max_not_sum_and_order_invariant() -> None:
    """Duplicate variants credit the best rank once; order does not matter."""

    shared = _candidate(rank=1)
    second = _candidate(chunk=shared.chunk_id, rank=5)
    other = _candidate(rank=2)
    left = fuse_channels(dense=((shared, other), (second,)))
    right = fuse_channels(dense=((second,), (other, shared)))
    assert [item.chunk_id for item in left] == [item.chunk_id for item in right]
    expected = rrf_contribution(1)
    top = next(item for item in left if item.chunk_id == shared.chunk_id)
    assert top.channel_score == pytest.approx(expected)


def test_caps_hold_across_variants() -> None:
    """Dense variants cannot multiply the 100-candidate cap."""

    overflow = tuple(_candidate(rank=index) for index in range(1, DENSE_CANDIDATE_CAP + 20))
    fused = fuse_channels(dense=(overflow, overflow, overflow))
    assert len(fused) <= PREFUSION_UNION_CAP
    assert len({item.chunk_id for item in fused}) == len(fused)


def test_metadata_factor_is_clamped() -> None:
    """Authority/title/temporal product cannot exceed 1.15."""

    item = _candidate(rank=1)
    fused = fuse_channels(dense=((item,),), metadata_factors={item.chunk_id: 9.0})
    unclamped = rrf_contribution(1) * 9.0
    assert fused[0].channel_score < unclamped
    assert fused[0].channel_score == pytest.approx(rrf_contribution(1) * 1.15)


def test_unknown_date_cannot_win_latest() -> None:
    """Latest ignores undated documents."""

    dated = _candidate()
    undated = _candidate()
    records = {
        dated.chunk_id: TemporalDocument(
            dated.chunk_id,
            effective_at=datetime(2024, 6, 1, tzinfo=UTC),
        ),
        undated.chunk_id: TemporalDocument(undated.chunk_id, effective_at=None),
    }
    kept = apply_temporal_policy(
        (undated, dated),
        records,
        intent=TemporalIntent.LATEST,
        target_date=None,
    )
    assert [item.chunk_id for item in kept] == [dated.chunk_id]
    with pytest.raises(ValueError, match="naive_datetime_forbidden"):
        TemporalDocument(
            dated.chunk_id,
            effective_at=datetime(2024, 6, 1),
        )


def test_as_of_and_recent_use_utc() -> None:
    """as_of keeps versions effective on or before the target day."""

    item = _candidate()
    records = {
        item.chunk_id: TemporalDocument(
            item.chunk_id,
            effective_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
    }
    kept = apply_temporal_policy(
        (item,),
        records,
        intent=TemporalIntent.AS_OF,
        target_date=date(2024, 6, 1),
    )
    assert kept == (item,)
    empty = apply_temporal_policy(
        (item,),
        records,
        intent=TemporalIntent.AS_OF,
        target_date=date(2024, 5, 31),
    )
    assert empty == ()


def test_assemble_degrades_bm25_and_refuses_full_summary() -> None:
    """ParadeDB outage is visible; uncovered headings block a full-summary claim."""

    dense = _candidate(rank=1)
    result = assemble_hybrid(
        dense_variants=((dense,),),
        bm25_variants=(),
        term_variants=(),
        bm25_fallback=RetrievalFallbackReason.BM25_UNAVAILABLE,
        want_full_summary=True,
        heading_inventory=("Overview", "Appendix"),
        covered_headings=("Overview",),
        principal_scope_hash="abc",
        query_normalized="query",
        visibility_generation=1,
    )
    assert result.fallback_reason is RetrievalFallbackReason.BM25_UNAVAILABLE
    assert result.coverage.signal is CoverageSignal.BM25_DEGRADED
    assert "Appendix" in result.coverage.uncovered_headings
    assert "bm25_unavailable" in result.coverage.notes


def test_media_and_negation_signals() -> None:
    """Media-only and unscoped negation emit signed coverage routes."""

    item = _candidate()
    media = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=(),
        media_dependence=True,
        principal_scope_hash="abc",
        query_normalized="chart",
        visibility_generation=1,
    )
    assert media.coverage.signal is CoverageSignal.MEDIA_LIMITATION
    negation = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=(),
        negation_scope="set_complement",
        principal_scope_hash="abc",
        query_normalized="not allowed",
        visibility_generation=1,
    )
    assert negation.coverage.signal is CoverageSignal.NEGATION_UNSCOPED


def test_cache_key_changes_with_visibility_and_forbids_unknown_profile() -> None:
    """Cache keys include visibility generation and reject unknown profile IDs."""

    first = hybrid_cache_key(
        principal_scope_hash="p",
        query_normalized="q",
        visibility_generation=1,
    )
    second = hybrid_cache_key(
        principal_scope_hash="p",
        query_normalized="q",
        visibility_generation=2,
    )
    assert first != second
    with pytest.raises(ValueError, match="unknown_retrieval_profile"):
        hybrid_cache_key(
            principal_scope_hash="p",
            query_normalized="q",
            retrieval_profile_id="admin",
            visibility_generation=1,
        )
    payload = cache_payload((uuid4(),), (1,))
    assert "snippet" not in payload


def test_deadline_zero_does_not_run_channels() -> None:
    """A spent deadline records timeout instead of launching channel work."""

    ran = {"value": False}

    def job() -> str:
        """Mark that the channel ran.

        Returns:
            Sentinel string.
        """

        ran["value"] = True
        return "ok"

    completed, timed_out, exhausted = run_channels_parallel(
        {"dense": job},
        deadline_seconds=0,
    )
    assert completed == {}
    assert timed_out == ("dense",)
    assert exhausted is True
    assert ran["value"] is False


def test_more_than_three_variants_is_rejected() -> None:
    """Fusion refuses a fourth query variant."""

    lists = tuple((_candidate(rank=1),) for _ in range(4))
    with pytest.raises(FusionError, match="more_than_three_variants"):
        fuse_channels(dense=lists)


def test_conflict_and_historical_signals() -> None:
    """Equal authorities emit conflict; one-unit history is weak evidence."""

    left = _candidate(rank=1)
    right = _candidate(rank=1)
    conflict = assemble_hybrid(
        dense_variants=((left,),),
        bm25_variants=((right,),),
        term_variants=(),
        contradictory_ids=(left.chunk_id, right.chunk_id),
        principal_scope_hash="abc",
        query_normalized="conflict",
        visibility_generation=1,
    )
    assert conflict.coverage.signal is CoverageSignal.CONFLICT
    assert set(conflict.coverage.conflict_chunk_ids) == {
        left.chunk_id,
        right.chunk_id,
    }
    historical = assemble_hybrid(
        dense_variants=((left,),),
        bm25_variants=(),
        term_variants=(),
        historical_relationship=True,
        principal_scope_hash="abc",
        query_normalized="after handoff",
        visibility_generation=1,
    )
    assert historical.coverage.signal is CoverageSignal.WEAK_EVIDENCE
    assert "historical_needs_two_units" in historical.coverage.notes


def test_current_drops_expired_and_recent_uses_window() -> None:
    """Current skips expired versions; recent keeps the 90-day UTC window."""

    current = _candidate()
    expired = _candidate()
    old = _candidate()
    now = datetime(2024, 8, 14, tzinfo=UTC)
    records = {
        current.chunk_id: TemporalDocument(
            current.chunk_id,
            effective_at=datetime(2024, 7, 1, tzinfo=UTC),
        ),
        expired.chunk_id: TemporalDocument(
            expired.chunk_id,
            effective_at=datetime(2024, 7, 2, tzinfo=UTC),
            expired=True,
        ),
        old.chunk_id: TemporalDocument(
            old.chunk_id,
            effective_at=datetime(2023, 1, 1, tzinfo=UTC),
        ),
    }
    kept_current = apply_temporal_policy(
        (current, expired),
        records,
        intent=TemporalIntent.CURRENT,
        target_date=None,
        now=now,
    )
    assert [item.chunk_id for item in kept_current] == [current.chunk_id]
    kept_recent = apply_temporal_policy(
        (current, old),
        records,
        intent=TemporalIntent.RECENT,
        target_date=None,
        now=now,
    )
    assert [item.chunk_id for item in kept_recent] == [current.chunk_id]


def test_equal_score_tie_break_uses_effective_date() -> None:
    """Equal RRF scores prefer the later UTC effective date, then canonical ID."""

    older = _candidate(rank=1)
    newer = _candidate(rank=1)
    records = {
        older.chunk_id: TemporalDocument(
            older.chunk_id,
            effective_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        newer.chunk_id: TemporalDocument(
            newer.chunk_id,
            effective_at=datetime(2024, 6, 1, tzinfo=UTC),
        ),
    }
    fused = fuse_channels(
        dense=((older,),),
        term=((newer,),),
        temporal_records=records,
    )
    assert [item.chunk_id for item in fused] == [newer.chunk_id, older.chunk_id]
