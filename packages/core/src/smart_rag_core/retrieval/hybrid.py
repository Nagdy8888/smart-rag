"""Assemble Hybrid results: caps, RRF, temporal policy, coverage, degradation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.retrieval.cache_key import hybrid_cache_key
from smart_rag_core.retrieval.coverage import (
    CoverageSignal,
    HybridCoverage,
    conflict_coverage,
    coverage_for_summary,
    media_limitation_coverage,
    negation_coverage,
)
from smart_rag_core.retrieval.coverage_score import attach_numeric_coverage
from smart_rag_core.retrieval.frozen_profile import load_frozen_profile
from smart_rag_core.retrieval.fusion import RetrievalChannel, cap_channel, fuse_channels
from smart_rag_core.retrieval.profiles import (
    BM25_SCAN_ID_CAP,
    HYBRID_DEADLINE_SECONDS,
    HYBRID_DEFAULT_PROFILE_ID,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.temporal import (
    TemporalDocument,
    TemporalIntent,
    apply_temporal_policy,
)
from smart_rag_core.retrieval.types import RetrievalCandidate


@dataclass(frozen=True, slots=True)
class HybridRetrievalResult:
    """Packet 4 Hybrid retrieval object. No answer text.

    Attributes:
        fused: Authorized unique candidates after RRF and temporal policy.
        coverage: Coverage/refusal/conflict/degradation signal.
        fallback_reason: Channel-level fallback, usually BM25 outage or none.
        deadline_exhausted: True when a channel missed the remaining deadline.
        cache_key: Versioned ID-only cache key.
        scanned_bm25: BM25 IDs scanned before recheck, for evidence.
        channel_hits: Independent channels that retrieved each fused ID.
    """

    fused: tuple[RetrievalCandidate, ...]
    coverage: HybridCoverage
    fallback_reason: RetrievalFallbackReason
    deadline_exhausted: bool
    cache_key: str
    scanned_bm25: tuple[UUID, ...] = ()
    channel_hits: dict[UUID, frozenset[str]] | None = None


def assemble_hybrid(
    *,
    dense_variants: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_variants: tuple[tuple[RetrievalCandidate, ...], ...],
    term_variants: tuple[tuple[RetrievalCandidate, ...], ...],
    bm25_fallback: RetrievalFallbackReason = RetrievalFallbackReason.NONE,
    temporal_intent: TemporalIntent = TemporalIntent.NONE,
    target_date: date | None = None,
    temporal_records: dict[UUID, TemporalDocument] | None = None,
    want_full_summary: bool = False,
    heading_inventory: tuple[str, ...] = (),
    covered_headings: tuple[str, ...] = (),
    media_dependence: bool = False,
    negation_scope: str = "none",
    contradictory_ids: tuple[UUID, ...] = (),
    historical_relationship: bool = False,
    principal_scope_hash: str,
    query_normalized: str,
    visibility_generation: int,
    metadata_factors: dict[UUID, float] | None = None,
    scanned_bm25: tuple[UUID, ...] = (),
    now: datetime | None = None,
    query_type: QueryType = QueryType.FACTUAL,
    query_class: QueryClass | None = None,
    required_terms: tuple[str, ...] = (),
    matched_terms: tuple[str, ...] = (),
    subquestion_count: int = 1,
    supported_subquestions: int | None = None,
    rerank_top_support: float | None = None,
    exact_phrase_or_code: bool = False,
    profile_ok: bool = True,
    pre_recheck_count: int | None = None,
    authorized_count: int | None = None,
    context_ok: bool = True,
    deadline_exhausted: bool = False,
) -> HybridRetrievalResult:
    """Fuse capped channel lists and attach coverage diagnostics.

    Args:
        dense_variants: At most three dense lists.
        bm25_variants: At most three authorized BM25 lists.
        term_variants: At most three term lists.
        bm25_fallback: ``bm25_unavailable`` degrades to dense+term.
        temporal_intent: UTC temporal policy.
        target_date: ``as_of`` target.
        temporal_records: Effective/published timestamps.
        want_full_summary: Whole-document request.
        heading_inventory: Current major headings.
        covered_headings: Headings present in fused evidence.
        media_dependence: Figure-only required evidence.
        negation_scope: Profile negation enum.
        contradictory_ids: Conflict fixture IDs.
        historical_relationship: Profile historical-relationship flag.
        principal_scope_hash: Cache principal hash.
        query_normalized: Normalized query used in the cache key.
        visibility_generation: ACL/visibility generation.
        metadata_factors: Optional multiplicative factors.
        scanned_bm25: BM25 IDs scanned before recheck (≤ 300).
        now: Optional frozen UTC clock.
        query_type: Profile query type for coverage minima.
        query_class: Evaluation class for the frozen threshold.
        required_terms: Required codes/entities/terms.
        matched_terms: Required terms found in authorized evidence.
        subquestion_count: Decomposition size.
        supported_subquestions: Supported subquestions.
        rerank_top_support: Optional rerank support feature.
        exact_phrase_or_code: Exact lookup winner.
        profile_ok: Query profile succeeded.
        pre_recheck_count: Channel IDs before authorization recheck.
        authorized_count: Recheck survivors.
        context_ok: Parent/context expansion stayed authorized.
        deadline_exhausted: True when a parallel channel missed the retrieval
            slice. Independent of BM25 degradation.

    Returns:
        Hybrid result with at most 205 unique IDs.

    Raises:
        UnknownRetrievalProfileError: If the frozen default profile is missing.
        FrozenProfileMutationError: If the frozen artifact hash drifted.
    """

    load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    dense_capped = tuple(
        cap_channel(variant, RetrievalChannel.DENSE) for variant in dense_variants
    )
    degraded = bm25_fallback in {
        RetrievalFallbackReason.BM25_UNAVAILABLE,
        RetrievalFallbackReason.BM25_VERSION_MISMATCH,
        RetrievalFallbackReason.TIMEOUT,
    }
    bm25_capped = (
        ()
        if degraded
        else tuple(
            cap_channel(variant, RetrievalChannel.BM25) for variant in bm25_variants
        )
    )
    term_capped = tuple(
        cap_channel(variant, RetrievalChannel.TERM) for variant in term_variants
    )
    fused = fuse_channels(
        dense=dense_capped,
        bm25=bm25_capped,
        term=term_capped,
        metadata_factors=metadata_factors,
        temporal_records=temporal_records,
    )
    fused = apply_temporal_policy(
        fused,
        temporal_records or {},
        intent=temporal_intent,
        target_date=target_date,
        now=now,
    )
    coverage = coverage_for_summary(
        fused=fused,
        heading_inventory=heading_inventory,
        covered_headings=covered_headings,
        want_full_summary=want_full_summary,
    )
    media = media_limitation_coverage(media_dependence=media_dependence)
    if media is not None:
        coverage = media
    negation = negation_coverage(negation_scope=negation_scope)
    if negation is not None:
        coverage = negation
    conflict = conflict_coverage(fused, contradictory_ids=contradictory_ids)
    if conflict is not None:
        coverage = conflict
    if historical_relationship and len(fused) < 2:
        coverage = HybridCoverage(
            signal=CoverageSignal.WEAK_EVIDENCE,
            uncovered_headings=coverage.uncovered_headings,
            conflict_chunk_ids=coverage.conflict_chunk_ids,
            notes=(*coverage.notes, "historical_needs_two_units"),
        )
    if degraded:
        coverage = HybridCoverage(
            signal=CoverageSignal.BM25_DEGRADED,
            uncovered_headings=coverage.uncovered_headings,
            conflict_chunk_ids=coverage.conflict_chunk_ids,
            notes=(*coverage.notes, "bm25_unavailable"),
        )
    key = hybrid_cache_key(
        principal_scope_hash=principal_scope_hash,
        query_normalized=query_normalized,
        retrieval_profile_id=HYBRID_DEFAULT_PROFILE_ID,
        visibility_generation=visibility_generation,
    )
    if len(scanned_bm25) > BM25_SCAN_ID_CAP:
        scanned_bm25 = scanned_bm25[:BM25_SCAN_ID_CAP]
    hits: dict[UUID, set[str]] = defaultdict(set)
    for variant in dense_capped:
        for item in variant:
            hits[item.chunk_id].add("dense")
    for variant in bm25_capped:
        for item in variant:
            hits[item.chunk_id].add("bm25")
    for variant in term_capped:
        for item in variant:
            hits[item.chunk_id].add("term")
    channel_hits = {chunk_id: frozenset(names) for chunk_id, names in hits.items()}
    coverage = attach_numeric_coverage(
        coverage,
        fused=fused,
        channel_hits=channel_hits,
        query_type=query_type,
        query_class=query_class,
        required_terms=required_terms,
        matched_terms=matched_terms,
        subquestion_count=subquestion_count,
        supported_subquestions=supported_subquestions,
        rerank_top_support=rerank_top_support,
        exact_phrase_or_code=exact_phrase_or_code,
        profile_ok=profile_ok,
        pre_recheck_count=pre_recheck_count,
        authorized_count=authorized_count,
        context_ok=context_ok,
    )
    return HybridRetrievalResult(
        fused=fused,
        coverage=coverage,
        fallback_reason=bm25_fallback,
        deadline_exhausted=deadline_exhausted,
        cache_key=key,
        scanned_bm25=scanned_bm25,
        channel_hits=channel_hits,
    )


def run_channels_parallel(
    jobs: dict[str, Callable[[], object]],
    *,
    deadline_seconds: float = HYBRID_DEADLINE_SECONDS,
) -> tuple[dict[str, object], tuple[str, ...], bool]:
    """Run channel callables in parallel and record timeouts separately.

    Args:
        jobs: Mapping of channel name to zero-argument callables.
        deadline_seconds: Remaining Hybrid deadline share.

    Returns:
        Completed results, timed-out names, and whether the deadline exhausted.

    Side Effects:
        Executes the callables in worker threads. Does not start answer
        generation.
    """

    if deadline_seconds <= 0:
        return {}, tuple(jobs), True
    executor = ThreadPoolExecutor(max_workers=max(1, len(jobs)))
    try:
        futures = {executor.submit(job): name for name, job in jobs.items()}
        done, pending = wait(futures, timeout=deadline_seconds)
        timed_out = tuple(futures[item] for item in pending)
        for item in pending:
            item.cancel()
        completed: dict[str, object] = {}
        for item in done:
            completed[futures[item]] = item.result()
        return completed, timed_out, bool(timed_out)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
