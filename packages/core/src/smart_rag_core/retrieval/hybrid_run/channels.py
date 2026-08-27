"""Hybrid channel collect, unpack, restrict, and flatten helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeGuard, cast
from uuid import UUID

from smart_rag_core.retrieval.hybrid_run.types import (
    CandidateList,
    VariantLists,
)
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
)
from smart_rag_core.retrieval.types import (
    Bm25RetrievalResult,
    DenseRetrievalResult,
    RetrievalCandidate,
    TermRetrievalResult,
)
from smart_rag_core.security.identity import CallerContext


def _is_candidate_tuple(value: object) -> TypeGuard[CandidateList]:
    """Return whether ``value`` is a tuple of retrieval candidates.

    Args:
        value: Channel job payload or an inner list.

    Returns:
        True when ``value`` is a tuple whose first item is a candidate, or
        empty. Matches the existing unpack ``isinstance`` checks.
    """

    if not isinstance(value, tuple):
        return False
    items = cast(tuple[object, ...], value)
    return not items or isinstance(items[0], RetrievalCandidate)


def _is_variant_tuple(value: object) -> TypeGuard[VariantLists]:
    """Return whether ``value`` is a tuple of per-variant candidate lists.

    Args:
        value: Channel job payload.

    Returns:
        True when ``value`` is a non-empty tuple whose first item is a tuple.
    """

    if not isinstance(value, tuple) or not value:
        return False
    items = cast(tuple[object, ...], value)
    return isinstance(items[0], tuple)


def collect_dense_lists(
    retrieve: Callable[..., object],
    *,
    caller: CallerContext,
    texts: tuple[str, ...],
    vectors: tuple[tuple[float, ...], ...],
) -> VariantLists:
    """Run dense retrieve once per fused query vector.

    Args:
        retrieve: Bound ``DenseRetriever.retrieve`` or a test double.
        caller: Server-derived identity.
        texts: Query forms aligned with ``vectors``.
        vectors: Query embeddings.

    Returns:
        Per-variant dense candidate lists.
    """

    lists: list[CandidateList] = []
    for _text, vector in zip(texts, vectors, strict=False):
        result = retrieve(caller=caller, query_embedding=list(vector))
        if isinstance(result, DenseRetrievalResult):
            lists.append(result.candidates)
        elif isinstance(result, tuple):
            lists.append(cast(CandidateList, result))
    return tuple(lists)


def collect_term_lists(
    retrieve: Callable[..., object],
    *,
    caller: CallerContext,
    texts: tuple[str, ...],
) -> VariantLists:
    """Run term retrieve once per fused query text.

    Args:
        retrieve: Bound ``TermRetriever.retrieve`` or a test double.
        caller: Server-derived identity.
        texts: Query forms.

    Returns:
        Per-variant term candidate lists.
    """

    lists: list[CandidateList] = []
    for text in texts:
        result = retrieve(caller=caller, query_text=text)
        if isinstance(result, TermRetrievalResult):
            lists.append(result.candidates)
        elif isinstance(result, tuple):
            lists.append(cast(CandidateList, result))
    return tuple(lists)


def restrict_channel_candidates(
    dense_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_result: Bm25RetrievalResult,
    term_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    version_id: UUID | None,
) -> tuple[
    tuple[tuple[RetrievalCandidate, ...], ...],
    Bm25RetrievalResult,
    tuple[tuple[RetrievalCandidate, ...], ...],
]:
    """Keep only candidates whose version matches the caller filter.

    Args:
        dense_lists: Per-variant dense lists.
        bm25_result: Authorized BM25 survivors.
        term_lists: Per-variant term lists.
        version_id: Version filter, or ``None`` to keep every candidate.

    Returns:
        Filtered dense lists, BM25 result, and term lists.
    """

    if version_id is None:
        return dense_lists, bm25_result, term_lists

    def _keep(
        candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[RetrievalCandidate, ...]:
        """Filter one candidate list to ``version_id``.

        Args:
            candidates: Authorized candidates.

        Returns:
            Candidates for the requested version only.
        """

        return tuple(item for item in candidates if item.version_id == version_id)

    filtered_dense = tuple(_keep(variant) for variant in dense_lists)
    filtered_bm25_candidates = _keep(bm25_result.candidates)
    filtered_bm25 = Bm25RetrievalResult(
        scanned_ids=tuple(item.chunk_id for item in filtered_bm25_candidates),
        candidates=filtered_bm25_candidates,
        fallback_reason=bm25_result.fallback_reason,
    )
    filtered_term = tuple(_keep(variant) for variant in term_lists)
    return filtered_dense, filtered_bm25, filtered_term


def flatten_channel_candidates(
    dense_lists: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_candidates: tuple[RetrievalCandidate, ...],
    term_lists: tuple[tuple[RetrievalCandidate, ...], ...],
) -> tuple[RetrievalCandidate, ...]:
    """Flatten dense, BM25, and term candidates for temporal lookup.

    Args:
        dense_lists: Per-variant dense lists.
        bm25_candidates: Authorized BM25 survivors.
        term_lists: Per-variant term lists.

    Returns:
        Deduplicated candidates in first-seen order.
    """

    seen: set[UUID] = set()
    ordered: list[RetrievalCandidate] = []
    for variant in dense_lists:
        for item in variant:
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            ordered.append(item)
    for item in bm25_candidates:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        ordered.append(item)
    for variant in term_lists:
        for item in variant:
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            ordered.append(item)
    return tuple(ordered)


def unpack_dense(
    value: object,
) -> tuple[VariantLists, RetrievalFallbackReason]:
    """Normalize a dense channel job result.

    Args:
        value: Job return value or ``None`` when the job was absent.

    Returns:
        Variant lists and a named dense fallback when the channel failed.
    """

    if value is None:
        return (), RetrievalFallbackReason.NONE
    if isinstance(value, DenseRetrievalResult):
        return (value.candidates,), value.fallback_reason
    if _is_candidate_tuple(value):
        if not value:
            return (), RetrievalFallbackReason.NONE
        return (value,), RetrievalFallbackReason.NONE
    if _is_variant_tuple(value):
        return value, RetrievalFallbackReason.NONE
    return (), RetrievalFallbackReason.DENSE_UNAVAILABLE


def unpack_term(
    value: object,
) -> tuple[VariantLists, RetrievalFallbackReason]:
    """Normalize a term channel job result.

    Args:
        value: Job return value or ``None`` when the job was absent.

    Returns:
        Variant lists and a named term fallback when the channel failed.
    """

    if value is None:
        return (), RetrievalFallbackReason.NONE
    if isinstance(value, TermRetrievalResult):
        return (value.candidates,), RetrievalFallbackReason.NONE
    if _is_candidate_tuple(value):
        if not value:
            return (), RetrievalFallbackReason.NONE
        return (value,), RetrievalFallbackReason.NONE
    if _is_variant_tuple(value):
        return value, RetrievalFallbackReason.NONE
    return (), RetrievalFallbackReason.TERM_UNAVAILABLE


def unpack_bm25(value: object) -> Bm25RetrievalResult:
    """Normalize a BM25 channel job result.

    Args:
        value: Job return value or ``None``.

    Returns:
        ID-only BM25 result. Missing jobs are empty with ``none``.
    """

    if isinstance(value, Bm25RetrievalResult):
        return value
    if _is_candidate_tuple(value) and value:
        return Bm25RetrievalResult(scanned_ids=(), candidates=value)
    if _is_variant_tuple(value) and value[0] and _is_candidate_tuple(value[0]):
        return Bm25RetrievalResult(scanned_ids=(), candidates=value[0])
    return Bm25RetrievalResult(scanned_ids=(), candidates=())


def compose_fallback(
    *,
    dense_reason: RetrievalFallbackReason,
    term_reason: RetrievalFallbackReason,
    bm25_fallback: RetrievalFallbackReason,
    deadline_exhausted: bool,
) -> RetrievalFallbackReason:
    """Choose the retrieve-level named fallback.

    Args:
        dense_reason: Dense channel outcome.
        term_reason: Term channel outcome.
        bm25_fallback: BM25 outage, version mismatch, timeout, or none.
        deadline_exhausted: True when any parallel job timed out.

    Returns:
        Highest-priority named reason. ``none`` when channels completed.
    """

    if dense_reason is RetrievalFallbackReason.DENSE_UNAVAILABLE:
        return RetrievalFallbackReason.DENSE_UNAVAILABLE
    if term_reason is RetrievalFallbackReason.TERM_UNAVAILABLE:
        return RetrievalFallbackReason.TERM_UNAVAILABLE
    if bm25_fallback is not RetrievalFallbackReason.NONE:
        return bm25_fallback
    if deadline_exhausted:
        return RetrievalFallbackReason.TIMEOUT
    return RetrievalFallbackReason.NONE


def identity_rerank(
    _query: str,
    pool: tuple[RerankPassage, ...],
    _deadline: float,
) -> tuple[tuple[RerankRanking, ...], None, RerankFallbackReason]:
    """Keep fused pool order without a model call.

    Args:
        _query: Unused original query.
        pool: Authorized rerank pool.
        _deadline: Unused remaining slice.

    Returns:
        Identity rankings, no usage, and ``none`` fallback.
    """

    rankings = tuple(
        RerankRanking(
            chunk_id=item.candidate.chunk_id,
            rank=index + 1,
            support=1.0,
        )
        for index, item in enumerate(pool)
    )
    return rankings, None, RerankFallbackReason.NONE
