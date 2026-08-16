"""Typed graph retrieval results, locators, and query counters.

Canonical chunk IDs and locators are the only evidence coordinates. Vendor
descriptions, keywords, file paths, and reference ordinals are omitted.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.retrieval.graph import GraphLimitationCode


class GraphQueryCounters(BaseModel):
    """Query-time callback and search counters.

    Attributes:
        keyword_extract: LightRAG keyword-role LLM calls. Must stay ``0``.
        answer_generate: LightRAG query-role LLM calls. Must stay ``0``.
        support_searches: Query-time Hybrid/support searches. Must stay ``0``.
        repair_hybrid_searches: Repair Hybrid searches. Must stay ``0``.
        embed: Embedding gateway batches (query vectors are expected).
        vendor_queries: ``aquery_data`` invocations on this path.
        candidates_returned: Clamped vendor candidates before resolver drops.
        candidates_supported: Candidates that survived every resolver check.
    """

    model_config = ConfigDict(frozen=True)

    keyword_extract: int = Field(ge=0)
    answer_generate: int = Field(ge=0)
    support_searches: int = Field(ge=0)
    repair_hybrid_searches: int = Field(ge=0)
    embed: int = Field(default=0, ge=0)
    vendor_queries: int = Field(default=0, ge=0)
    candidates_returned: int = Field(default=0, ge=0)
    candidates_supported: int = Field(default=0, ge=0)


class GraphLimitation(BaseModel):
    """One typed limitation. Restricted names/counts are never attached.

    Attributes:
        code: Stable limitation identifier.
        count: Optional authorized-only count. ``None`` means undisclosed.
    """

    model_config = ConfigDict(frozen=True)

    code: GraphLimitationCode
    count: int | None = Field(default=None, ge=0)


class GraphCanonicalLocator(BaseModel):
    """Citation coordinates from canonical rows. Never vendor chunk text.

    Attributes:
        chunk_id: Canonical chunk UUID.
        document_id: Owning document.
        version_id: Current authorized version.
        page_number: Page index when stored.
        section_path: Heading ancestry.
        sheet_name: Spreadsheet sheet from provenance locators.
        range_ref: Cell or range from provenance locators.
        source_url: HTML/crawl URL from provenance locators.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    page_number: int | None = None
    section_path: tuple[str, ...] = ()
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None


class GraphResolvedCandidate(BaseModel):
    """One wholly surviving relationship, entity, or path candidate.

    Attributes:
        kind: Application object kind.
        object_id: Application statement, entity, or path-edge id.
        canonical_chunk_ids: Supporting canonical chunks after recheck.
        document_id: Owning document.
        version_id: Current version.
        support: Accepted mapping support in ``[0.80, 1]``.
        confidence: Same as support for Packet 5 (no second model score).
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1, max_length=32)
    object_id: str = Field(min_length=1, max_length=64)
    canonical_chunk_ids: tuple[UUID, ...]
    document_id: UUID
    version_id: UUID
    support: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class GraphPath(BaseModel):
    """One bounded application path reconstructed from surviving statements.

    Attributes:
        statement_ids: Ordered application statement IDs.
        path_edge_ids: Matching path-edge IDs when mapped.
        hops: Statement count, at most three.
        canonical_chunk_ids: Union of supporting chunks.
    """

    model_config = ConfigDict(frozen=True)

    statement_ids: tuple[str, ...]
    path_edge_ids: tuple[str, ...] = ()
    hops: int = Field(ge=1, le=3)
    canonical_chunk_ids: tuple[UUID, ...] = ()


class GraphSteeringExpansion(BaseModel):
    """One global topic/entity expansion. Never evidence.

    Attributes:
        topic: Vendor entity name used only to steer later Hybrid (Phase 6).
    """

    model_config = ConfigDict(frozen=True)

    topic: str = Field(min_length=1, max_length=512)


class RollingSurvivalWindow(BaseModel):
    """Recorded rolling survival interface. Not a live alert backend.

    Attributes:
        sample_count: Persisted samples, at most 20.
        mean: Mean of stored ratios, or ``None`` when empty.
        below_alert_threshold: True when 20 samples exist and mean < 0.80.
    """

    model_config = ConfigDict(frozen=True)

    sample_count: int = Field(ge=0, le=20)
    mean: float | None = None
    below_alert_threshold: bool = False


class GraphRetrievalResult(BaseModel):
    """Authoritative graph retrieval outcome for Phase 6 to consume.

    Attributes:
        mode: ``local``, ``hybrid``, or ``global``.
        candidates: Surviving application objects only.
        paths: At most six bounded paths.
        steering: At most three global expansions. Empty for local/hybrid.
        locators: Canonical locators for surviving chunk IDs.
        graph_survival_ratio: Supported/returned, or ``None`` when none.
        partial_readiness_count: Authorized company-visible Hybrid-ready
            versions that are not yet queryable in the graph. Always a
            non-negative count.
        acl_blindness_count: Authorized-only restricted graph-ineligible
            count. Never includes documents the caller cannot read.
        limitations: Typed signals without restricted names.
        diagnostics: Machine-readable drop reasons. No document titles.
        counters: Query-time callback and search counters.
        rolling_survival: Durable 20-sample interface.
    """

    model_config = ConfigDict(frozen=True)

    mode: str
    candidates: tuple[GraphResolvedCandidate, ...] = ()
    paths: tuple[GraphPath, ...] = ()
    steering: tuple[GraphSteeringExpansion, ...] = ()
    locators: tuple[GraphCanonicalLocator, ...] = ()
    graph_survival_ratio: float | None = None
    partial_readiness_count: int = Field(default=0, ge=0)
    acl_blindness_count: int = Field(default=0, ge=0)
    limitations: tuple[GraphLimitation, ...] = ()
    diagnostics: tuple[str, ...] = ()
    counters: GraphQueryCounters
    rolling_survival: RollingSurvivalWindow = RollingSurvivalWindow(sample_count=0)


class GraphInspectNode(BaseModel):
    """One authorized inspection row. No vendor prose.

    Attributes:
        object_type: entity, statement, or path_edge.
        object_id: Application object id.
        chunk_id: Supporting canonical chunk.
        document_id: Owning document.
        version_id: Current version.
        support: Mapping support.
        hop: Distance from the seed, 0-3.
    """

    model_config = ConfigDict(frozen=True)

    object_type: str = Field(min_length=1, max_length=32)
    object_id: str = Field(min_length=1, max_length=64)
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    support: float = Field(ge=0.0, le=1.0)
    hop: int = Field(ge=0, le=3)


class GraphInspectResult(BaseModel):
    """Bounded inspection outcome through the identical resolver.

    Attributes:
        nodes: At most 200 authorized rows.
        locators: Canonical locators for those chunks.
        limitations: Workspace/temporal/outage signals.
        row_count: ``len(nodes)`` after the 200-row cap.
        depth: Requested depth after clamping to 3.
    """

    model_config = ConfigDict(frozen=True)

    nodes: tuple[GraphInspectNode, ...] = ()
    locators: tuple[GraphCanonicalLocator, ...] = ()
    limitations: tuple[GraphLimitation, ...] = ()
    row_count: int = Field(default=0, ge=0, le=200)
    depth: int = Field(default=1, ge=1, le=3)
