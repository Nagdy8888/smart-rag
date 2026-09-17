"""Hybrid branch execution and canonical chunk loading."""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
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
    QueryPreparation,
)
from smart_rag_core.query_routing.protocols import HybridRetrieveLike
from smart_rag_core.retrieval.cache_store import RetrievalCacheMode
from smart_rag_core.retrieval.context import ContextFn
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.security.identity import CallerContext


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
        remaining: Remaining seconds.
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
        )
    retrieve_kwargs: dict[str, object] = {
        "query": spec.query_text,
        "caller": caller,
        "profile": prep.profile,
        "deadline_seconds": min(remaining, 8.0),
    }
    if spec.bypass_retrieval_cache:
        retrieve_kwargs["cache_mode"] = RetrievalCacheMode.COLD_BYPASS
    try:
        outcome = hybrid_retriever.retrieve(**retrieve_kwargs)
    except TypeError:
        retrieve_kwargs.pop("cache_mode", None)
        outcome = hybrid_retriever.retrieve(**retrieve_kwargs)
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
    )


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
