"""Unit tests for BM25 variant fairness and named outage."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.retrieval.hybrid_run.channels import (
    cap_unique_across_variants,
    unpack_bm25,
)
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate


def _candidate(*, rank: int = 1) -> RetrievalCandidate:
    """Build one BM25 survivor.

    Args:
        rank: Channel rank.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=rank,
        channel_score=1.0,
    )


def test_one_bm25_variant_cannot_consume_the_cap() -> None:
    """Round-robin unique capping keeps later-variant evidence."""

    first = tuple(_candidate(rank=index) for index in range(1, 21))
    second_unique = _candidate(rank=1)
    second = (second_unique,)
    capped = cap_unique_across_variants((first, second), 10)
    kept = {item.chunk_id for variant in capped for item in variant}
    assert len(kept) == 10
    assert second_unique.chunk_id in kept
    assert first[0].chunk_id in kept


def test_duplicate_variant_ids_do_not_multiply_the_cap() -> None:
    """Exact duplicate copies across variants still count once."""

    shared = _candidate()
    extras = tuple(_candidate(rank=index) for index in range(1, 6))
    capped = cap_unique_across_variants(((shared, *extras), (shared,)), 3)
    unique = {item.chunk_id for variant in capped for item in variant}
    assert len(unique) == 3
    assert shared.chunk_id in unique


def test_bm25_outage_is_named_without_fake_success() -> None:
    """ParadeDB failures stay empty with bm25_unavailable."""

    result = unpack_bm25(
        Bm25RetrievalResult(
            scanned_ids=(),
            candidates=(),
            fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
        )
    )
    assert result.candidates == ()
    assert result.fallback_reason is RetrievalFallbackReason.BM25_UNAVAILABLE
