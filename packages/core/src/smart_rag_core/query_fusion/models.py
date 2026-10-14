"""Typed Combined fusion inputs, scored passages, and algorithm records."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_rag_core.query_fusion.constants import (
    FUSION_FINAL_EVIDENCE_MAX,
    GRAPH_WEIGHT,
)
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.formulas import assert_constant_graph_weight


class FusionAlgorithm(StrEnum):
    """Allow-listed Combined ranking algorithm. Selected by ablation."""

    RESOLVED_PATH_FUSION = "resolved_path_fusion"
    NAIVE_UNION = "naive_union"


class PassageOrigin(StrEnum):
    """How a canonical passage entered the Combined pool."""

    HYBRID = "hybrid"
    GRAPH_RESOLVED = "graph_resolved"
    BOTH = "both"


class HybridPassage(BaseModel):
    """One Hybrid canonical passage with post-rerank or allowed RRF rank.

    Attributes:
        chunk_id: Canonical chunk UUID string.
        document_id: Owning document UUID string.
        version_id: Current version UUID string.
        citation_text: Canonical Supabase passage text. Never a BM25 snippet.
        hybrid_rank: 1-based Hybrid rank.
        section_path: Heading ancestry for frozen section quotas.
        page_number: Page index when stored.
        sheet_name: Spreadsheet sheet from locators.
        range_ref: Cell or range from locators.
        source_url: Crawl URL from locators.
        authorized_current: Authoritative current-version/ACL survivor.
        deleted: True when the source was deleted. Fusion discards it.
        unauthorized: True when ACL forbids the caller. Fusion discards it.
        bm25_snippet: Forbidden evidence flag. Must stay false.
        content_kind: ``code``, ``table``, or ``figure`` when stored that way.
        figure_id: Stable figure id for an authorized image route.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=36)
    document_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    citation_text: str = Field(default="", max_length=16_384)
    hybrid_rank: int = Field(ge=1)
    section_path: tuple[str, ...] = ()
    page_number: int | None = None
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None
    authorized_current: bool = True
    deleted: bool = False
    unauthorized: bool = False
    bm25_snippet: Literal[False] = False
    content_kind: Literal["code", "table", "figure"] | None = None
    figure_id: str | None = None


class GraphPathInput(BaseModel):
    """One fully mapped application path used for graph_passage_strength.

    Attributes:
        statement_ids: Ordered surviving statement IDs.
        hops: Statement count, at most three.
        canonical_chunk_ids: Union of supporting canonical chunks.
        edge_chunk_ids: Per-hop supporting chunk IDs, aligned with statements.
        edge_supports: Per-hop mapping support, aligned with statements.
        fully_mapped: True only when every hop has support and chunks.
        unmapped: True when mapping is missing.
        stale: True when the mapped version is not current.
        deleted: True when a supporting source was deleted.
        unauthorized: True when ACL forbids a supporting source.
        missing_edge_support: True when any hop lacks support.
        native_prose: True when vendor description/reference was supplied.
        steering_only: True for GlobalSteering expansions. Never scored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement_ids: tuple[str, ...] = ()
    hops: int = Field(ge=1, le=3)
    canonical_chunk_ids: tuple[str, ...] = ()
    edge_chunk_ids: tuple[tuple[str, ...], ...] = ()
    edge_supports: tuple[float, ...] = ()
    fully_mapped: bool = False
    unmapped: bool = False
    stale: bool = False
    deleted: bool = False
    unauthorized: bool = False
    missing_edge_support: bool = False
    native_prose: bool = False
    steering_only: bool = False

    @model_validator(mode="after")
    def _align_edges(self) -> GraphPathInput:
        """Reject hop/support misalignment on fully mapped paths.

        Returns:
            This path.

        Raises:
            ValueError: If a fully mapped path has mismatched hop metadata.
        """

        if self.fully_mapped and (
            len(self.edge_supports) != self.hops or len(self.statement_ids) != self.hops
        ):
            raise ValueError("path_edge_alignment")
        if (
            self.fully_mapped
            and self.edge_chunk_ids
            and len(self.edge_chunk_ids) != self.hops
        ):
            raise ValueError("path_edge_alignment")
        return self


class GraphPassage(BaseModel):
    """Canonical locator/text for a graph-resolved chunk. Never vendor prose.

    Attributes:
        chunk_id: Canonical chunk UUID string.
        document_id: Owning document UUID string.
        version_id: Current version UUID string.
        citation_text: Canonical Supabase text. Empty until Hybrid or a
            canonical loader supplies it. Native graph prose is forbidden.
        section_path: Heading ancestry.
        page_number: Page index when stored.
        sheet_name: Spreadsheet sheet from locators.
        range_ref: Cell or range from locators.
        source_url: Crawl URL from locators.
        authorized_current: Authoritative survivor.
        deleted: Deleted source flag.
        unauthorized: ACL denial flag.
        native_prose: True when the text is a vendor description/reference.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=36)
    document_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    citation_text: str = Field(default="", max_length=16_384)
    section_path: tuple[str, ...] = ()
    page_number: int | None = None
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None
    authorized_current: bool = True
    deleted: bool = False
    unauthorized: bool = False
    native_prose: bool = False


class FusionInput(BaseModel):
    """Inputs for Hybrid-only, naive union, or resolved-path fusion.

    Attributes:
        requested_route: Envelope family reserved at admit.
        effective_route: Planner family before fusion degrade.
        hybrid_passages: Authorized Hybrid evidence with ranks.
        graph_paths: Candidate application paths.
        graph_passages: Canonical locators/text for graph chunk IDs.
        graph_survival_ratio: Resolver survival, or None when no graph branch.
        graph_fallback_reason: Typed graph degrade reason when present.
        graph_timeout: True when LightRAG missed its deadline.
        keyword_extract_count: Must stay 0.
        lightrag_answer_generate_count: Must stay 0.
        graph_weight: Frozen 0.50. Non-matching values fail closed.
        tune_on_holdout: Must stay false.
        global_steering_chunk_ids: Expansions that must not receive graph score.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_route: str
    effective_route: str
    hybrid_passages: tuple[HybridPassage, ...] = ()
    graph_paths: tuple[GraphPathInput, ...] = ()
    graph_passages: tuple[GraphPassage, ...] = ()
    graph_survival_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    graph_fallback_reason: str | None = None
    graph_timeout: bool = False
    keyword_extract_count: Literal[0] = 0
    lightrag_answer_generate_count: Literal[0] = 0
    graph_weight: float = GRAPH_WEIGHT
    tune_on_holdout: bool = False
    global_steering_chunk_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _frozen_weight(self) -> FusionInput:
        """Reject model-generated fusion weights at parse time.

        Returns:
            This input.

        Raises:
            FusionError: If the graph weight is not frozen ``0.50``.
        """

        assert_constant_graph_weight(self.graph_weight)
        if self.tune_on_holdout:
            raise FusionError("holdout_tuned_configuration")
        return self


class ScoredPassage(BaseModel):
    """One canonical passage after Combined scoring, before or after quotas.

    Attributes:
        chunk_id: Canonical chunk UUID string.
        document_id: Owning document UUID string.
        version_id: Current version UUID string.
        citation_text: Canonical citation text.
        hybrid_rank: 1-based Hybrid rank, or None when absent.
        graph_rank: 1-based graph rank, or None when absent.
        graph_passage_strength: Max path contribution, or None.
        path_support: Winning path support, or None.
        combined_score: RRF plus optional agreement multiplier.
        origin: Hybrid, graph-resolved, or both.
        graph_discovered_only: True when Hybrid did not rank this passage.
        section_path: Heading ancestry.
        page_number: Page index.
        sheet_name: Sheet name.
        range_ref: Cell or range.
        source_url: Source URL.
        statement_ids: Supporting path statement IDs.
        content_kind: ``code``, ``table``, or ``figure`` when stored that way.
        figure_id: Stable figure id for an authorized image route.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    document_id: str
    version_id: str
    citation_text: str = ""
    hybrid_rank: int | None = Field(default=None, ge=1)
    graph_rank: int | None = Field(default=None, ge=1)
    graph_passage_strength: float | None = None
    path_support: float | None = None
    combined_score: float
    origin: PassageOrigin
    graph_discovered_only: bool
    section_path: tuple[str, ...] = ()
    page_number: int | None = None
    sheet_name: str | None = None
    range_ref: str | None = None
    source_url: str | None = None
    statement_ids: tuple[str, ...] = ()
    content_kind: Literal["code", "table", "figure"] | None = None
    figure_id: str | None = None


class FusionResult(BaseModel):
    """Combined or Hybrid-effective evidence after scoring and quotas.

    Attributes:
        algorithm: Selected ranking algorithm.
        config_hash: SHA-256 of the frozen constant set plus algorithm.
        requested_route: Envelope family reserved at admit.
        effective_route: Family after graph degrade, if any.
        fallback_reason: Typed degrade/limitation reason.
        evidence: At most 12 canonical units.
        dropped_graph_only: Graph-only IDs removed by the 40% cap.
        discarded_paths: Path drop reasons without document titles.
        graph_discovered_only_ratio: Graph-only / final count, or 0.
        keyword_extract_count: Must stay 0.
        lightrag_answer_generate_count: Must stay 0.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    algorithm: FusionAlgorithm
    config_hash: str = Field(min_length=64, max_length=64)
    requested_route: str
    effective_route: str
    fallback_reason: str | None = None
    evidence: tuple[ScoredPassage, ...] = Field(max_length=FUSION_FINAL_EVIDENCE_MAX)
    dropped_graph_only: tuple[str, ...] = ()
    discarded_paths: tuple[str, ...] = ()
    graph_discovered_only_ratio: float = Field(ge=0.0, le=1.0)
    keyword_extract_count: Literal[0] = 0
    lightrag_answer_generate_count: Literal[0] = 0


class AblationCaseScore(BaseModel):
    """One fixture's Hybrid-only / union / fusion outcomes.

    Attributes:
        case_id: Stable fixture id.
        gold_chunk_ids: Canonical IDs required for path/answer success.
        hybrid_success: True when Hybrid-only evidence covers gold IDs.
        union_success: True when naive union covers gold IDs.
        fusion_success: True when resolved-path fusion covers gold IDs.
        hybrid_citation_completeness: Gold recall under Hybrid-only.
        union_citation_completeness: Gold recall under union.
        fusion_citation_completeness: Gold recall under fusion.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    gold_chunk_ids: tuple[str, ...]
    hybrid_success: bool
    union_success: bool
    fusion_success: bool
    hybrid_citation_completeness: float = Field(ge=0.0, le=1.0)
    union_citation_completeness: float = Field(ge=0.0, le=1.0)
    fusion_citation_completeness: float = Field(ge=0.0, le=1.0)


class AblationReport(BaseModel):
    """Development/qualification ablation. Holdout labels are forbidden.

    Attributes:
        cases: Per-fixture scores.
        hybrid_success_rate: Mean Hybrid-only success.
        union_success_rate: Mean naive-union success.
        fusion_success_rate: Mean resolved-path fusion success.
        union_completeness: Mean union citation completeness.
        fusion_completeness: Mean fusion citation completeness.
        selected_algorithm: Winner, or union when fusion does not beat it.
        fusion_beats_union: Whether fusion wins success and completeness.
        combined_minus_hybrid_pp: Fusion minus Hybrid success, in pp.
        live_combined_gain_status: ``unverified`` until live mapping eval.
        config_hash: Frozen configuration digest.
        holdout_used: Must stay false.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: tuple[AblationCaseScore, ...]
    hybrid_success_rate: float
    union_success_rate: float
    fusion_success_rate: float
    union_completeness: float
    fusion_completeness: float
    selected_algorithm: FusionAlgorithm
    fusion_beats_union: bool
    combined_minus_hybrid_pp: float
    live_combined_gain_status: Literal["unverified", "measured"] = "unverified"
    config_hash: str = Field(min_length=64, max_length=64)
    holdout_used: Literal[False] = False
