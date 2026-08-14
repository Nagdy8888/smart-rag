"""Normalized weighted RRF with max-across-variants, never sum-across-variants."""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from uuid import UUID

from smart_rag_core.retrieval.profiles import (
    BM25_AUTHORIZED_SURVIVOR_CAP,
    CHANNEL_WEIGHT_BM25,
    CHANNEL_WEIGHT_DENSE,
    CHANNEL_WEIGHT_TERM,
    DENSE_CANDIDATE_CAP,
    METADATA_FACTOR_MAX,
    METADATA_FACTOR_MIN,
    PREFUSION_UNION_CAP,
    RRF_K,
    TERM_CANDIDATE_CAP,
)
from smart_rag_core.retrieval.temporal import TemporalDocument
from smart_rag_core.retrieval.types import RetrievalCandidate


class RetrievalChannel(StrEnum):
    """Independent Hybrid channels. Raw scores never mix across channels."""

    DENSE = "dense"
    BM25 = "bm25"
    TERM = "term"


CHANNEL_CAPS: dict[RetrievalChannel, int] = {
    RetrievalChannel.DENSE: DENSE_CANDIDATE_CAP,
    RetrievalChannel.BM25: BM25_AUTHORIZED_SURVIVOR_CAP,
    RetrievalChannel.TERM: TERM_CANDIDATE_CAP,
}

CHANNEL_WEIGHTS: dict[RetrievalChannel, float] = {
    RetrievalChannel.DENSE: CHANNEL_WEIGHT_DENSE,
    RetrievalChannel.BM25: CHANNEL_WEIGHT_BM25,
    RetrievalChannel.TERM: CHANNEL_WEIGHT_TERM,
}


class FusionError(ValueError):
    """Raised when fusion inputs violate Packet 4 caps or identity rules."""


def clamp_metadata_factor(value: float) -> float:
    """Clamp the multiplicative metadata product to ``[1.0, 1.15]``.

    Args:
        value: Unclamped product of allow-listed factors.

    Returns:
        Clamped factor. Current-version and ACL are hard filters, not factors.
    """

    return min(METADATA_FACTOR_MAX, max(METADATA_FACTOR_MIN, value))


def rrf_contribution(rank: int, *, k: int = RRF_K) -> float:
    """Return one reciprocal-rank contribution.

    Args:
        rank: 1-based channel rank.
        k: Plan-fixed RRF smoother. Must remain 60 until Packet 6.

    Returns:
        ``1 / (k + rank)``.

    Raises:
        FusionError: If rank is not a positive integer.
    """

    if rank < 1:
        raise FusionError("invalid_channel_rank")
    if k != RRF_K:
        raise FusionError("rrf_k_not_allowlisted")
    return 1.0 / (float(k) + float(rank))


def cap_channel(
    candidates: tuple[RetrievalCandidate, ...],
    channel: RetrievalChannel,
) -> tuple[RetrievalCandidate, ...]:
    """Apply the post-variant-dedup channel cap.

    Args:
        candidates: Already-deduplicated candidates for one channel.
        channel: Channel whose cap applies.

    Returns:
        At most the channel cap, preserving order.

    Raises:
        FusionError: If a client tries to exceed the cap by passing a longer
            list that was not truncated. Callers must truncate; this function
            truncates rather than trusting a client limit.
    """

    limit = CHANNEL_CAPS[channel]
    return candidates[:limit]


def max_rrf_by_id(
    variant_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    channel: RetrievalChannel,
) -> dict[UUID, float]:
    """Take the best RRF contribution per ID across variants.

    Summing variant contributions is forbidden. Duplicate variants and
    reversed variant order must not change the per-ID maximum.

    Args:
        variant_lists: Per-variant ranked lists for one channel.
        channel: Channel being fused. Used only for the cap.

    Returns:
        Mapping of chunk ID to max RRF contribution.
    """

    best: dict[UUID, float] = {}
    for variant in variant_lists:
        capped = cap_channel(variant, channel)
        for candidate in capped:
            contribution = rrf_contribution(candidate.channel_rank)
            current = best.get(candidate.chunk_id)
            if current is None or contribution > current:
                best[candidate.chunk_id] = contribution
    return best


def fuse_channels(
    *,
    dense: tuple[tuple[RetrievalCandidate, ...], ...] = (),
    bm25: tuple[tuple[RetrievalCandidate, ...], ...] = (),
    term: tuple[tuple[RetrievalCandidate, ...], ...] = (),
    metadata_factors: dict[UUID, float] | None = None,
    temporal_records: dict[UUID, TemporalDocument] | None = None,
) -> tuple[RetrievalCandidate, ...]:
    """Fuse dense, BM25, and term lists with weighted RRF.

    Args:
        dense: Per-variant dense lists.
        bm25: Per-variant authorized BM25 lists.
        term: Per-variant term lists.
        metadata_factors: Optional per-ID multiplicative factors already
            clamped or clampable into ``[1.0, 1.15]``.
        temporal_records: Optional UTC dates used only for equal-score
            tie-breaks (effective date, published date, then canonical ID).

    Returns:
        Unique candidates ordered by fused score descending, then effective
        date, published date, then canonical ID, truncated to 205.

    Raises:
        FusionError: If more than three variant lists are supplied per channel.
    """

    if max(len(dense), len(bm25), len(term)) > 3:
        raise FusionError("more_than_three_variants")
    dense_scores = max_rrf_by_id(dense, RetrievalChannel.DENSE)
    bm25_scores = max_rrf_by_id(bm25, RetrievalChannel.BM25)
    term_scores = max_rrf_by_id(term, RetrievalChannel.TERM)
    identity: dict[UUID, RetrievalCandidate] = {}
    for variant in (*dense, *bm25, *term):
        for candidate in variant:
            identity.setdefault(candidate.chunk_id, candidate)
    fused_scores: dict[UUID, float] = defaultdict(float)
    for chunk_id, score in dense_scores.items():
        fused_scores[chunk_id] += CHANNEL_WEIGHTS[RetrievalChannel.DENSE] * score
    for chunk_id, score in bm25_scores.items():
        fused_scores[chunk_id] += CHANNEL_WEIGHTS[RetrievalChannel.BM25] * score
    for chunk_id, score in term_scores.items():
        fused_scores[chunk_id] += CHANNEL_WEIGHTS[RetrievalChannel.TERM] * score
    factors = metadata_factors or {}
    records = temporal_records or {}
    ranked: list[tuple[float, float, float, str, RetrievalCandidate]] = []
    for chunk_id, score in fused_scores.items():
        factor = clamp_metadata_factor(factors.get(chunk_id, 1.0))
        candidate = identity[chunk_id]
        record = records.get(chunk_id)
        effective_ts = 0.0
        published_ts = 0.0
        if record is not None and record.effective_at is not None:
            effective_ts = record.effective_at.timestamp()
        if record is not None and record.published_at is not None:
            published_ts = record.published_at.timestamp()
        ranked.append(
            (
                -(score * factor),
                -effective_ts,
                -published_ts,
                str(chunk_id),
                candidate,
            )
        )
    ranked.sort()
    fused: list[RetrievalCandidate] = []
    for index, (neg_score, _, _, _, candidate) in enumerate(
        ranked[:PREFUSION_UNION_CAP], start=1
    ):
        fused.append(
            RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                version_id=candidate.version_id,
                channel_rank=index,
                channel_score=-neg_score,
                match_kind=candidate.match_kind,
            )
        )
    return tuple(fused)
