"""Hybrid assemble kwargs, fusion call, and closed-result helpers."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from datetime import date
from uuid import UUID

from smart_rag_core.evaluation.schema import ExpectedProfile, QueryType
from smart_rag_core.retrieval.coverage import CoverageSignal, HybridCoverage
from smart_rag_core.retrieval.hybrid import HybridRetrievalResult, assemble_hybrid
from smart_rag_core.retrieval.hybrid_run.profile_fields import str_list_field
from smart_rag_core.retrieval.hybrid_run.types import (
    EMBED_TEXT_CAP,
    AssembleHybridKwargs,
    HybridRunResult,
    VariantLists,
)
from smart_rag_core.retrieval.profiles import (
    CHANNEL_MIN_SECONDS,
    CHANNEL_PHASE_RESERVE_SECONDS,
    MAX_NORMALIZED_QUERY_CHARS,
    RERANK_RESERVED_SECONDS,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.temporal import TemporalDocument, TemporalIntent
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


def hybrid_assemble_kwargs(
    *,
    dense_variants: VariantLists,
    bm25_variants: VariantLists,
    term_variants: VariantLists,
    bm25_fallback: RetrievalFallbackReason,
    temporal_intent: TemporalIntent,
    target_date: date | None,
    temporal_records: dict[UUID, TemporalDocument],
    want_full_summary: bool,
    media_dependence: bool,
    negation_scope: str,
    historical_relationship: bool,
    principal_scope_hash: str,
    query_normalized: str,
    visibility_generation: int,
    scanned_bm25: tuple[UUID, ...],
    query_type: QueryType,
    required_terms: tuple[str, ...],
    matched_terms: tuple[str, ...],
    subquestion_count: int,
    deadline_exhausted: bool,
) -> AssembleHybridKwargs:
    """Pack the shared ``assemble_hybrid`` kwargs for one retrieve.

    Args:
        dense_variants: Per-variant dense lists.
        bm25_variants: Authorized BM25 lists.
        term_variants: Per-variant term lists.
        bm25_fallback: BM25 outage, timeout, or none.
        temporal_intent: UTC temporal policy.
        target_date: ``as_of`` target.
        temporal_records: Effective timestamps by chunk.
        want_full_summary: Whole-document request.
        media_dependence: Figure-only required evidence.
        negation_scope: Profile negation enum.
        historical_relationship: Profile historical-relationship flag.
        principal_scope_hash: Cache principal hash.
        query_normalized: Normalized query used in the cache key.
        visibility_generation: ACL/visibility generation.
        scanned_bm25: BM25 IDs scanned before recheck.
        query_type: Profile query type.
        required_terms: Codes and exact terms.
        matched_terms: Terms already matched; Hybrid retrieve passes empty.
        subquestion_count: Decomposition size. ``0`` means none.
        deadline_exhausted: True when a parallel channel missed the slice.

    Returns:
        Typed kwargs unpacked into both ``assemble_hybrid`` calls.
    """

    return {
        "dense_variants": dense_variants,
        "bm25_variants": bm25_variants,
        "term_variants": term_variants,
        "bm25_fallback": bm25_fallback,
        "temporal_intent": temporal_intent,
        "target_date": target_date,
        "temporal_records": temporal_records,
        "want_full_summary": want_full_summary,
        "media_dependence": media_dependence,
        "negation_scope": negation_scope,
        "historical_relationship": historical_relationship,
        "principal_scope_hash": principal_scope_hash,
        "query_normalized": query_normalized,
        "visibility_generation": visibility_generation,
        "scanned_bm25": scanned_bm25,
        "query_type": query_type,
        "required_terms": required_terms,
        "matched_terms": matched_terms,
        "subquestion_count": subquestion_count,
        "deadline_exhausted": deadline_exhausted,
    }


def call_assemble_hybrid(
    *,
    heading_inventory: tuple[str, ...],
    covered_headings: tuple[str, ...],
    kwargs: AssembleHybridKwargs,
) -> HybridRetrievalResult:
    """Call ``assemble_hybrid`` with the same heading and channel arguments.

    Args:
        heading_inventory: Current major headings.
        covered_headings: Headings present in fused evidence.
        kwargs: Shared channel, temporal, and coverage arguments.

    Returns:
        The ``assemble_hybrid`` result for this heading snapshot.
    """

    return assemble_hybrid(
        heading_inventory=heading_inventory,
        covered_headings=covered_headings,
        **kwargs,
    )


def fail_closed_query(query: str) -> RetrievalFallbackReason | None:
    """Return a named fallback when the query must not retrieve.

    Args:
        query: Raw user query.

    Returns:
        ``retrieval_empty`` when blank or over ``MAX_NORMALIZED_QUERY_CHARS``.
    """

    normalized = normalize_arabic_v1(query)
    if normalized == "" or len(normalized) > MAX_NORMALIZED_QUERY_CHARS:
        return RetrievalFallbackReason.RETRIEVAL_EMPTY
    return None


def query_texts(
    query: str,
    profile: ExpectedProfile | None,
    selectors: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build unique embed texts: original, question sentence, then variants.

    Args:
        query: Original query.
        profile: Optional profile whose ``variants`` field is a string list.
        selectors: Authorized titles removed from the question sentence.

    Returns:
        At most four unique strings. The original stays first. The question
        sentence uses one slot, so a profile keeps at most two extra variants.
    """

    from smart_rag_core.retrieval.hybrid_run.search_text import question_search_text

    ordered = [query]
    seen = {query.strip()}
    search = question_search_text(query, selectors).strip()
    if search and search not in seen:
        seen.add(search)
        ordered.append(search)
    for variant in str_list_field(profile, "variants"):
        key = variant.strip()
        if key == "" or key in seen:
            continue
        seen.add(key)
        ordered.append(variant)
        if len(ordered) >= EMBED_TEXT_CAP:
            break
    return tuple(ordered)


def compute_principal_scope_hash(caller: CallerContext) -> str:
    """Hash caller identity for the ID-only cache key.

    Args:
        caller: Server-derived identity.

    Returns:
        SHA-256 hex digest. Raw user IDs are not logged here.
    """

    payload = (
        f"{caller.user_id}:{caller.rpc_role()}:{caller.rpc_authorization_version()}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def closed_result(
    reason: RetrievalFallbackReason,
    *,
    started: float,
    embedding_call_count: int = 0,
) -> HybridRunResult:
    """Build a fail-closed retrieve result with no evidence.

    Args:
        reason: Named fallback.
        started: ``perf_counter`` timestamp from retrieve start.
        embedding_call_count: ``1`` when a gateway call was attempted.

    Returns:
        Empty ranked/evidence result with measured ``first_evidence_ms``.
    """

    return HybridRunResult(
        ranked_ids=(),
        evidence=(),
        coverage=HybridCoverage(
            signal=CoverageSignal.WEAK_EVIDENCE,
            notes=(reason.value,),
        ),
        fallback_reason=reason,
        deadline_exhausted=reason is RetrievalFallbackReason.TIMEOUT,
        first_evidence_ms=elapsed_ms(started),
        embedding_call_count=embedding_call_count,
        rerank_call_count=0,
    )


def elapsed_ms(started: float) -> float:
    """Return milliseconds since ``started``.

    Args:
        started: ``time.perf_counter`` value.

    Returns:
        Non-negative milliseconds.
    """

    return max(0.0, (time.perf_counter() - started) * 1000.0)


def remaining_slice_seconds(*, slice_seconds: float, slice_started: float) -> float:
    """Return unused seconds in the channel-plus-rerank slice.

    Embedding runs before ``slice_started`` and is not subtracted from the
    8s bound. The 8s value itself is not raised. OpenAI rerank starts only
    when this remainder is at least ``RERANK_RESERVED_SECONDS``.

    Args:
        slice_seconds: Channel-plus-rerank bound.
        slice_started: ``perf_counter`` when parallel channels started.

    Returns:
        Remaining seconds, never negative.
    """

    return max(0.0, slice_seconds - (time.perf_counter() - slice_started))


def fused_first_evidence_ms(*, started: float, fused_at: float | None) -> float:
    """Return milliseconds until fused IDs exist, else until fail-closed.

    Rerank, MMR, parent expansion, and context preload after fusion are
    excluded so first-evidence is not the end-to-end retrieve wall time.

    Args:
        started: Retrieve start ``perf_counter``.
        fused_at: ``perf_counter`` when fused candidate IDs first exist.

    Returns:
        Non-negative milliseconds.
    """

    if fused_at is None:
        return elapsed_ms(started)
    return max(0.0, (fused_at - started) * 1000.0)


def channel_phase_deadline_seconds(slice_seconds: float) -> float:
    """Return how long channels may run inside one retrieve slice.

    The channel phase ends early enough that post-channel work
    (``CHANNEL_PHASE_RESERVE_SECONDS``) plus the rerank reserve
    (``RERANK_RESERVED_SECONDS``) still fit in the slice. The result is at
    least ``CHANNEL_MIN_SECONDS`` and never more than the slice itself.

    Args:
        slice_seconds: Retrieve slice in seconds (already clamped by the
            Hybrid branch).

    Returns:
        Channel wait in seconds. A channel still running then is reported as
        timed out by ``run_channels_parallel``.
    """

    reserved = RERANK_RESERVED_SECONDS + CHANNEL_PHASE_RESERVE_SECONDS
    return min(slice_seconds, max(CHANNEL_MIN_SECONDS, slice_seconds - reserved))
