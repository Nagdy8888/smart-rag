"""Typed Hybrid retrieval candidates and channel results."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from smart_rag_core.retrieval.profiles import (
    DenseMode,
    RetrievalFallbackReason,
)


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """One authorized candidate ID from a single channel.

    Attributes:
        chunk_id: Canonical chunk UUID.
        document_id: Canonical document UUID.
        version_id: Current document version UUID.
        channel_rank: 1-based rank within the channel list.
        channel_score: Channel-local score (distance, BM25, or trigram).
        match_kind: Optional term-channel match kind.
    """

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    channel_rank: int
    channel_score: float
    match_kind: str | None = None


@dataclass(frozen=True, slots=True)
class DenseRetrievalResult:
    """Dense channel outcome.

    Attributes:
        mode: ANN, exact, or weak-evidence admission refusal.
        candidates: Ordered authorized candidates.
        authorized_count: Admission count used for exact fallback.
        fallback_reason: Weak-evidence or none.
    """

    mode: DenseMode
    candidates: tuple[RetrievalCandidate, ...]
    authorized_count: int
    fallback_reason: RetrievalFallbackReason = RetrievalFallbackReason.NONE


@dataclass(frozen=True, slots=True)
class TermRetrievalResult:
    """Term channel outcome.

    Attributes:
        candidates: Ordered authorized term matches.
        query_normalized: ``arabic_norm_v1`` form used for the query.
        empty_channel: True when no terms/aliases matched.
    """

    candidates: tuple[RetrievalCandidate, ...]
    query_normalized: str
    empty_channel: bool


@dataclass(frozen=True, slots=True)
class Bm25RetrievalResult:
    """BM25 ID-only scan plus authoritative recheck outcome.

    Attributes:
        scanned_ids: Canonical IDs scanned before recheck (≤ 300).
        candidates: Authorized survivors after recheck (≤ 75).
        fallback_reason: Outage, version mismatch, timeout, or none.
    """

    scanned_ids: tuple[UUID, ...]
    candidates: tuple[RetrievalCandidate, ...]
    fallback_reason: RetrievalFallbackReason = RetrievalFallbackReason.NONE
