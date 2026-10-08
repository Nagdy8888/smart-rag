"""Hybrid branch execution and canonical chunk loading."""

from __future__ import annotations

from typing import Literal, Protocol, cast
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.usage_caps import ANSWER_STAGE_MIN_SECONDS
from smart_rag_core.query_fusion.models import HybridPassage
from smart_rag_core.query_routing.branch_results import (
    coverage_bits,
    fallback_reason_text,
    ranked_ids,
)
from smart_rag_core.query_routing.constants import (
    FALLBACK_RETRIEVERS_UNBOUND,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.models import (
    BranchResult,
    BranchSpec,
    HybridBranchDiagnostics,
    QueryPreparation,
)
from smart_rag_core.query_routing.protocols import HybridRetrieveLike
from smart_rag_core.retrieval.cache_store import RetrievalCacheMode
from smart_rag_core.retrieval.context import ContextFn
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.profiles import (
    HYBRID_CHANNEL_NAMES,
    HYBRID_STAGE_TIMING_KEYS,
    RERANK_INVALID_SUBCODES,
    RERANK_POOL_SIZE,
    RETRIEVAL_SLICE_SECONDS,
)
from smart_rag_core.security.identity import CallerContext


class _HybridRetrieveWithCacheLike(Protocol):
    """Hybrid retrieve surface that accepts a cache mode."""

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
        cache_mode: RetrievalCacheMode = RetrievalCacheMode.NORMAL,
    ) -> object:
        """Run one Hybrid retrieve, optionally bypassing the rank cache.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile.
            deadline_seconds: Remaining retrieval slice.
            cache_mode: Rank-cache mode. ``cold_bypass`` skips get/put.

        Returns:
            Object with ``ranked_ids`` and ``coverage`` attributes.
        """

        ...


def run_hybrid(
    spec: BranchSpec,
    *,
    prep: QueryPreparation,
    runtime: AuthorizedRuntimeContext,
    caller: CallerContext,
    remaining: float,
    hybrid_retriever: HybridRetrieveLike | None,
    whole_document: bool,
    chunk_loader: ContextFn | None,
) -> BranchResult:
    """Invoke HybridRetriever when bound.

    Args:
        spec: Hybrid spec.
        prep: Preparation.
        runtime: Authorized context.
        caller: Caller snapshot.
        remaining: Remaining seconds. The slice passed to retrieve is
            ``max(2, min(remaining - 8, 10))`` seconds.
        hybrid_retriever: Optional retriever.
        whole_document: Whether section coverage must be 1.0.
        chunk_loader: Canonical text loader for ranked-ID fallbacks.

    Returns:
        Hybrid branch result. BM25 snippets are never marked as evidence.
    """

    if hybrid_retriever is None:
        return BranchResult(
            branch_id=spec.branch_id,
            kind=spec.kind,
            family=spec.family,
            run_id=runtime.run_id,
            reservation_id=runtime.reservation_id,
            query_text=spec.query_text,
            status="degraded",
            fallback_reason=FALLBACK_RETRIEVERS_UNBOUND,
            hybrid_diagnostics=hybrid_diagnostics_from_outcome(
                None,
                effective_route=spec.family.value,
                fallback_reason=FALLBACK_RETRIEVERS_UNBOUND,
            ),
        )
    deadline_seconds = max(
        2.0,
        min(remaining - ANSWER_STAGE_MIN_SECONDS, RETRIEVAL_SLICE_SECONDS),
    )
    outcome: object
    if spec.bypass_retrieval_cache:
        cached = cast(_HybridRetrieveWithCacheLike, hybrid_retriever)
        try:
            outcome = cached.retrieve(
                query=spec.query_text,
                caller=caller,
                profile=prep.profile,
                deadline_seconds=deadline_seconds,
                cache_mode=RetrievalCacheMode.COLD_BYPASS,
                remaining_run_seconds=remaining,
            )
        except TypeError:
            outcome = hybrid_retriever.retrieve(
                query=spec.query_text,
                caller=caller,
                profile=prep.profile,
                deadline_seconds=deadline_seconds,
                remaining_run_seconds=remaining,
            )
    else:
        outcome = hybrid_retriever.retrieve(
            query=spec.query_text,
            caller=caller,
            profile=prep.profile,
            deadline_seconds=deadline_seconds,
            remaining_run_seconds=remaining,
        )
    ranked = ranked_ids(outcome)
    coverage_score, ratio, uncovered = coverage_bits(outcome, whole_document)
    status: Literal["ok", "degraded", "refused", "failed"] = "ok"
    fallback_text = fallback_reason_text(outcome)
    if whole_document and (ratio is None or ratio < WHOLE_DOCUMENT_SECTION_COVERAGE):
        status = "refused"
        fallback_text = "section_coverage_below_1"
    return BranchResult(
        branch_id=spec.branch_id,
        kind=spec.kind,
        family=spec.family,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        query_text=spec.query_text,
        ranked_ids=ranked,
        coverage_score=coverage_score,
        section_coverage_ratio=ratio,
        uncovered_headings=uncovered,
        fallback_reason=fallback_text,
        status=status,
        bm25_snippets_used=False,
        graph_prose_used=False,
        hybrid_evidence=hybrid_evidence(outcome, chunk_loader=chunk_loader),
        hybrid_diagnostics=hybrid_diagnostics_from_outcome(
            outcome,
            effective_route=spec.family.value,
            fallback_reason=fallback_text or "none",
        ),
    )


def hybrid_diagnostics_from_outcome(
    outcome: object | None,
    *,
    effective_route: str,
    fallback_reason: str | None,
) -> HybridBranchDiagnostics | None:
    """Build ID-only Hybrid diagnostics from one retrieve outcome.

    Args:
        outcome: Hybrid retrieve result, or ``None`` when unbound.
        effective_route: Executed branch family.
        fallback_reason: Named retrieve fallback already chosen by the
            branch.

    Returns:
        Frozen diagnostics, or ``None`` when required tokens are missing.

    Raises:
        ValueError: When an ID is not a UUID string.
    """

    coverage = getattr(outcome, "coverage", None) if outcome is not None else None
    source_resolution = ""
    profile_id = ""
    rerank_fallback = "none"
    if outcome is not None:
        source_resolution = str(getattr(outcome, "source_resolution", "") or "")
        profile_id = str(getattr(outcome, "retrieval_profile_id", "") or "")
        raw_rerank = str(getattr(outcome, "rerank_fallback", "") or "").strip()
        rerank_fallback = raw_rerank or "none"
    if not source_resolution or not profile_id or not fallback_reason:
        return None
    return HybridBranchDiagnostics(
        source_resolution=source_resolution,
        retrieval_profile_id=profile_id,
        fallback_reason=str(fallback_reason),
        rerank_fallback=rerank_fallback,
        rerank_call_count=int(getattr(outcome, "rerank_call_count", 0) or 0)
        if outcome is not None
        else 0,
        embedding_call_count=int(getattr(outcome, "embedding_call_count", 0) or 0)
        if outcome is not None
        else 0,
        first_evidence_ms=float(getattr(outcome, "first_evidence_ms", 0.0) or 0.0)
        if outcome is not None
        else 0.0,
        dense_ids=_uuid_ids(getattr(outcome, "dense_ids", ()), 100)
        if outcome is not None
        else (),
        bm25_ids=_uuid_ids(getattr(outcome, "bm25_ids", ()), 75)
        if outcome is not None
        else (),
        term_ids=_uuid_ids(getattr(outcome, "term_ids", ()), 30)
        if outcome is not None
        else (),
        fused_ids=_uuid_ids(getattr(outcome, "fused_ids", ()), 100)
        if outcome is not None
        else (),
        selected_ids=_uuid_ids(getattr(outcome, "selected_ids", ()), 12)
        if outcome is not None
        else (),
        rerank_pool_ids=_uuid_ids(getattr(outcome, "rerank_order", ()), 100)
        if outcome is not None
        else (),
        coverage_score=getattr(coverage, "coverage_score", None),
        term_coverage=getattr(coverage, "term_coverage", None),
        subquestion_coverage=getattr(coverage, "subquestion_coverage", None),
        evidence_ratio=getattr(coverage, "evidence_ratio", None),
        support_confidence=getattr(coverage, "support_confidence", None),
        effective_route=effective_route,
        stage_timings_ms=_stage_timings(getattr(outcome, "stage_timings_ms", None)),
        rerank_invalid_subcode=_invalid_subcode(
            getattr(outcome, "rerank_invalid_subcode", "")
        ),
        rerank_partial=_bounded_count(getattr(outcome, "rerank_appended_count", 0)) > 0,
        rerank_ranked_count=_bounded_count(getattr(outcome, "rerank_ranked_count", 0)),
        rerank_appended_count=_bounded_count(
            getattr(outcome, "rerank_appended_count", 0)
        ),
        channel_timed_out=_channel_names(getattr(outcome, "channel_timed_out", ())),
    )


def _uuid_ids(values: object, cap: int) -> tuple[str, ...]:
    """Copy UUID identifiers up to ``cap``.

    Args:
        values: Sequence of UUID or UUID strings.
        cap: Maximum retained IDs.

    Returns:
        UUID strings. Non-UUID items are omitted.
    """

    if isinstance(values, list):
        raw_items = tuple(cast(list[object], values))
    elif isinstance(values, tuple):
        raw_items = cast(tuple[object, ...], values)
    else:
        return ()
    kept: list[str] = []
    for item in raw_items[:cap]:
        text = str(item)
        try:
            UUID(text)
        except ValueError:
            continue
        kept.append(text)
    return tuple(kept)


def _stage_timings(value: object) -> dict[str, int]:
    """Keep allow-listed, non-negative integer stage timings.

    Args:
        value: ``stage_timings_ms`` from the retrieve outcome, or anything.

    Returns:
        A new dict with only known keys and non-negative ``int`` values.
        Booleans, floats, strings, and unknown keys are dropped, so a bad
        value never fails the branch.
    """

    if not isinstance(value, dict):
        return {}
    kept: dict[str, int] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str) or key not in HYBRID_STAGE_TIMING_KEYS:
            continue
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            continue
        kept[key] = item
    return kept


def _invalid_subcode(value: object) -> str:
    """Return an allow-listed rerank validation sub-code or empty.

    Args:
        value: ``rerank_invalid_subcode`` from the retrieve outcome.

    Returns:
        The value when it is in ``RERANK_INVALID_SUBCODES``, else ``""``.
    """

    if isinstance(value, str) and value in RERANK_INVALID_SUBCODES:
        return value
    return ""


def _channel_names(value: object) -> tuple[str, ...]:
    """Keep allow-listed, deduplicated, sorted channel names.

    Args:
        value: ``channel_timed_out`` from the retrieve outcome, or anything.

    Returns:
        Sorted names from ``HYBRID_CHANNEL_NAMES``. Other items are dropped,
        so a bad value never fails the branch.
    """

    if not isinstance(value, list | tuple):
        return ()
    items = cast(list[object] | tuple[object, ...], value)
    names = {item for item in items if isinstance(item, str)}
    return tuple(sorted(names & HYBRID_CHANNEL_NAMES))


def _bounded_count(value: object) -> int:
    """Return a rerank count in ``[0, RERANK_POOL_SIZE]``, else 0.

    Args:
        value: Count from the retrieve outcome, or anything.

    Returns:
        The integer when it is a non-boolean int in range, else ``0``.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    if value < 0 or value > RERANK_POOL_SIZE:
        return 0
    return value


def chunk_loader(
    hybrid_retriever: HybridRetrieveLike | None,
    caller: CallerContext,
) -> ContextFn | None:
    """Bind the Hybrid canonical-text loader when the retriever exposes it.

    Args:
        hybrid_retriever: Optional Hybrid retriever.
        caller: Server-derived caller.

    Returns:
        ``ContextFn`` or None when unbound.
    """

    if hybrid_retriever is None:
        return None
    factory = getattr(hybrid_retriever, "authorized_chunk_loader", None)
    if not callable(factory):
        return None
    loader = factory(caller)
    if not callable(loader):
        return None
    return cast(ContextFn, loader)


def load_chunk_contexts(
    chunk_ids: tuple[str, ...],
    chunk_loader: ContextFn | None,
) -> dict[str, ChunkContext]:
    """Load authorized canonical rows for one ID list.

    Args:
        chunk_ids: Canonical chunk UUID strings.
        chunk_loader: Optional ACL-rechecking loader.

    Returns:
        Mapping of chunk id string to authorized context. Missing,
        unauthorized, and unparsable IDs are omitted.
    """

    if chunk_loader is None or not chunk_ids:
        return {}
    parsed: list[UUID] = []
    for item in chunk_ids:
        try:
            parsed.append(UUID(str(item)))
        except ValueError:
            continue
    if not parsed:
        return {}
    loaded = chunk_loader(tuple(parsed))
    return {str(row.chunk_id): row for row in loaded}


def hybrid_evidence(
    outcome: object,
    *,
    chunk_loader: ContextFn | None,
) -> tuple[HybridPassage, ...]:
    """Snapshot Hybrid evidence units with 1-based post-rerank ranks.

    When evidence units are absent, RRF ``ranked_ids`` supply the allowed
    skip/fallback ranks. Canonical ``raw_text`` is loaded when a chunk
    loader is bound. Empty text is dropped and is never treated as a
    whole-passage citation.

    Args:
        outcome: Hybrid retrieve result.
        chunk_loader: Authorized canonical-text loader.

    Returns:
        Canonical Hybrid passages. BM25 snippets are never copied.
    """

    units = getattr(outcome, "evidence", ())
    records: list[HybridPassage] = []
    if units:
        unit_ids = tuple(str(unit.chunk_id) for unit in units)
        by_id = load_chunk_contexts(unit_ids, chunk_loader)
        for index, unit in enumerate(units, start=1):
            locator = getattr(unit, "locator", None)
            record = by_id.get(str(unit.chunk_id))
            if record is not None:
                text = record.raw_text
            elif chunk_loader is None:
                text = str(getattr(unit, "citation_text", "") or "")
            else:
                continue
            if not text.strip():
                continue
            records.append(
                HybridPassage(
                    chunk_id=str(unit.chunk_id),
                    document_id=str(
                        record.document_id if record is not None else unit.document_id
                    ),
                    version_id=str(
                        record.version_id if record is not None else unit.version_id
                    ),
                    citation_text=text,
                    hybrid_rank=index,
                    section_path=tuple(
                        record.section_path
                        if record is not None
                        else getattr(locator, "section_path", ()) or ()
                    ),
                    page_number=(
                        record.page_number
                        if record is not None
                        else getattr(locator, "page_number", None)
                    ),
                    sheet_name=(
                        record.sheet_name
                        if record is not None
                        else getattr(locator, "sheet_name", None)
                    ),
                    range_ref=(
                        record.range_ref
                        if record is not None
                        else getattr(locator, "range_ref", None)
                    ),
                    source_url=(
                        record.source_url
                        if record is not None
                        else getattr(locator, "source_url", None)
                    ),
                )
            )
        return tuple(records)
    ranked = tuple(str(item) for item in getattr(outcome, "ranked_ids", ()) or ())
    by_id = load_chunk_contexts(ranked, chunk_loader)
    for index, chunk_id in enumerate(ranked, start=1):
        record = by_id.get(chunk_id)
        if record is None:
            continue
        text = record.raw_text
        if not text.strip():
            continue
        records.append(
            HybridPassage(
                chunk_id=chunk_id,
                document_id=str(record.document_id),
                version_id=str(record.version_id),
                citation_text=text,
                hybrid_rank=index,
                section_path=record.section_path,
                page_number=record.page_number,
                sheet_name=record.sheet_name,
                range_ref=record.range_ref,
                source_url=record.source_url,
            )
        )
    return tuple(records)
