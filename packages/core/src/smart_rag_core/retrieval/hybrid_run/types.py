"""Hybrid-run types, locators, and result payloads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol, TypedDict
from uuid import UUID

from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.retrieval.coverage import HybridCoverage
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.temporal import TemporalDocument, TemporalIntent
from smart_rag_core.retrieval.types import RetrievalCandidate

FUSION_LIST_CAP = 3
EMBED_TEXT_CAP = 4

CandidateList = tuple[RetrievalCandidate, ...]
VariantLists = tuple[CandidateList, ...]
DenseRetrieveCall = Callable[..., object]
TermRetrieveCall = Callable[..., object]
Bm25RetrieveCall = Callable[..., object]
ChannelJob = Callable[[], object]


class DenseRetrieverLike(Protocol):
    """Object with a dense ``retrieve`` method used by Hybrid channel jobs.

    Attributes:
        retrieve: Bound dense retrieve callable or test double.
    """

    retrieve: DenseRetrieveCall


class Bm25RetrieverLike(Protocol):
    """Object with a BM25 ``retrieve`` method used by Hybrid channel jobs.

    Attributes:
        retrieve: Bound BM25 retrieve callable or test double.
    """

    retrieve: Bm25RetrieveCall


class TermRetrieverLike(Protocol):
    """Object with a term ``retrieve`` method used by Hybrid channel jobs.

    Attributes:
        retrieve: Bound term retrieve callable or test double.
    """

    retrieve: TermRetrieveCall


class AssembleHybridKwargs(TypedDict):
    """Keyword arguments shared by both Hybrid assemble calls in one retrieve.

    Attributes:
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
        deadline_exhausted: True when a parallel channel missed the slice.
    """

    dense_variants: VariantLists
    bm25_variants: VariantLists
    term_variants: VariantLists
    bm25_fallback: RetrievalFallbackReason
    temporal_intent: TemporalIntent
    target_date: date | None
    temporal_records: dict[UUID, TemporalDocument]
    want_full_summary: bool
    media_dependence: bool
    negation_scope: str
    historical_relationship: bool
    principal_scope_hash: str
    query_normalized: str
    visibility_generation: int
    scanned_bm25: tuple[UUID, ...]
    query_type: QueryType
    required_terms: tuple[str, ...]
    matched_terms: tuple[str, ...]
    deadline_exhausted: bool


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    """Citation coordinates from canonical rows, never BM25 snippets.

    Attributes:
        page_number: Page index from ``document_chunks.page_number``.
        section_path: Heading ancestry from ``section_path``.
        sheet_name: Spreadsheet sheet from provenance locators.
        range_ref: Cell or range from provenance locators.
        source_url: HTML/crawl URL from provenance locators.
    """

    page_number: int | None = None
    section_path: tuple[str, ...] = ()
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceUnit:
    """One authorized Hybrid evidence unit with canonical citation text.

    Attributes:
        chunk_id: Canonical chunk UUID.
        document_id: Document UUID.
        version_id: Current version UUID.
        citation_text: ``ChunkContext.raw_text`` only.
        locator: Page/section/sheet/range/URL from canonical provenance.
    """

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    citation_text: str
    locator: EvidenceLocator


@dataclass(frozen=True, slots=True)
class HybridRunResult:
    """Typed Hybrid retrieve outcome. No answer text.

    Attributes:
        ranked_ids: Authorized fused IDs in rank order (Recall@K input).
        evidence: At most 12 citation units with locators.
        coverage: Coverage/refusal diagnostics.
        fallback_reason: Named retrieve fallback, or ``none``.
        deadline_exhausted: True when a channel missed the retrieval slice.
        first_evidence_ms: Wall milliseconds until evidence or fail-closed
            status on this retrieve path (QT-LAT-001), not first answer token.
        embedding_call_count: ``0`` or ``1``. Variants share one batch.
        rerank_call_count: ``0`` or ``1`` from the one-shot reranker.
        cache_key: Versioned ID-only cache key when assembly ran.
    """

    ranked_ids: tuple[UUID, ...]
    evidence: tuple[EvidenceUnit, ...]
    coverage: HybridCoverage
    fallback_reason: RetrievalFallbackReason
    deadline_exhausted: bool
    first_evidence_ms: float
    embedding_call_count: int
    rerank_call_count: int
    cache_key: str = ""
