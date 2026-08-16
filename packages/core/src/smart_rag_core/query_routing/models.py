"""Typed preparation, plan, branch, and correction contracts for packet 2."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.query_fusion.models import (
    GraphPassage,
    GraphPathInput,
    HybridPassage,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    MAX_GRAPH_EXPANSIONS,
    PROVISIONAL_COVERAGE_THRESHOLD,
    SUBQUESTION_CEILING,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.tables.plan import TableQueryPlan


class RoutingSurface(StrEnum):
    """Where the run was admitted. Manual routing is diagnostic-only."""

    PRODUCTION = "production"
    DIAGNOSTIC = "diagnostic"


class BranchKind(StrEnum):
    """Direct retrieval invocation kind. Core routes never use a catalog LLM."""

    HYBRID = "hybrid"
    GRAPH_LOCAL = "graph_local"
    GRAPH_HYBRID = "graph_hybrid"
    GRAPH_GLOBAL_STEERING = "graph_global_steering"
    STRUCTURED_TABLE = "structured_table"
    GRAPH_INSPECTION = "graph_inspection"
    NO_RETRIEVAL = "no_retrieval"
    SCOPED_REFUSAL = "scoped_refusal"
    CITATION_LOOKUP = "citation_lookup"


class CorrectionKind(StrEnum):
    """The single global correction, or none. Never both kinds."""

    NONE = "none"
    HYBRID_TO_COMBINED = "hybrid_to_combined"
    SAME_ROUTE_RETRY = "same_route_retry"


class Phase6Extension(StrEnum):
    """Phase 6-only families that Phase 4 ``QueryType`` cannot produce."""

    GRAPH_INSPECTION = "graph_inspection"
    NO_RETRIEVAL = "no_retrieval"
    NONE = "none"


class MemoryRecord(BaseModel):
    """One untrusted conversation message loaded for preparation.

    Attributes:
        message_id: Canonical message UUID string.
        role: ``user``, ``assistant``, ``system``, or ``tool``.
        content: Truncated message text. Never a source document.
        created_at: ISO-8601 timestamp from Postgres.
        delimited: Instruction-safe delimited record for model input.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str = Field(min_length=1, max_length=36)
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(max_length=1500)
    created_at: str = Field(min_length=1, max_length=64)
    delimited: str = Field(min_length=1, max_length=2048)


class PreparationModelPayload(BaseModel):
    """One structured rewrite-plus-profile payload. Extra fields are forbidden.

    Attributes:
        rewrite: Optional standalone rewrite. Original remains the fallback.
        query_type: Optional inferred Phase 4 query type.
        subquestions: At most three strings.
        variants: At most three strings.
        hl_keywords: Precomputed high-level keywords. Never extracted later.
        ll_keywords: Precomputed low-level keywords. Never extracted later.
        retrieval_profile_id: Allow-listed Hybrid profile id when present.
        metadata_filters: Allow-listed filters.
        confidence: Closed unit interval.
        relationship_intent: Optional relationship signal from the model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rewrite: str | None = Field(default=None, max_length=2000)
    query_type: str | None = Field(default=None, max_length=64)
    subquestions: tuple[str, ...] = Field(default_factory=tuple, max_length=3)
    variants: tuple[str, ...] = Field(default_factory=tuple, max_length=3)
    hl_keywords: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    ll_keywords: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    retrieval_profile_id: str | None = Field(default=None, max_length=64)
    metadata_filters: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    relationship_intent: bool | None = None

    @model_validator(mode="after")
    def _bound_lists(self) -> PreparationModelPayload:
        """Reject a fourth subquestion or variant.

        Returns:
            This payload.

        Raises:
            ValueError: If more than three subquestions or variants appear.
        """

        if len(self.subquestions) > SUBQUESTION_CEILING:
            raise ValueError("fourth_subquestion")
        if len(self.variants) > SUBQUESTION_CEILING:
            raise ValueError("fourth_subquestion")
        return self


class QueryPreparation(BaseModel):
    """One typed preparation result. Every packet-2 field is required.

    Attributes:
        original: Unmodified user query. Always preserved.
        rewrite: Optional displayed rewrite. None when unused.
        profile: Frozen Phase 4 ``ExpectedProfile``.
        language: ``en``, ``ar``, or ``mixed``.
        temporal_intent: UTC-anchored temporal intent.
        timezone: ``UTC`` unless QUALITY_TARGETS signs another zone.
        hl_keywords: Precomputed high-level keywords.
        ll_keywords: Precomputed low-level keywords.
        entities: Entity strings.
        approved_aliases: Approved alias strings.
        exact_terms: Exact term list.
        dates: Date literals.
        numbers: Numeric literals.
        metadata_filters: Allow-listed filters.
        negation_scope: Negation enum.
        negation_confidence: Confidence for the negation scope.
        document_scope: Document/section/page scope text.
        section_scope: Section scope or ``none``.
        page_scope: Page scope or ``none``.
        media_intent: Figure/chart/diagram-only signal.
        historical_relationship: Past/as_of relationship signal.
        low_confidence_relationship: Ambiguous relationship kept for correction.
        relationship_intent: Relationship/multi-hop signal.
        decomposition: At most three subquestions.
        confidence: Overall preparation confidence.
        model_calls: ``0`` or ``1``. A second rewrite call is forbidden.
        fallback_reason: Profile/routing fallback code.
        intent_fidelity: Rewrite intent score against the original.
        entity_fidelity: Rewrite entity/code/alias score against the original.
        original_fallback_variant: Always the original query.
        query_type: Frozen Phase 4 query type string.
        phase6_extension: ``graph_inspection``, ``no_retrieval``, or ``none``.
        comparison: Whether this is a comparison subset of multi-part.
        table_intent: Structured-table signal.
        corpus_wide_theme: Corpus landscape/theme signal.
        whole_document_summary: Single-document full summary request.
        routing_surface: Production or diagnostic.
        manual_mode: True only when diagnostic manual routing was recorded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    original: str = Field(min_length=1, max_length=2000)
    rewrite: str | None = Field(default=None, max_length=2000)
    profile: ExpectedProfile
    language: str = Field(min_length=2, max_length=16)
    temporal_intent: str = Field(min_length=1, max_length=32)
    timezone: str = Field(min_length=1, max_length=64)
    hl_keywords: tuple[str, ...]
    ll_keywords: tuple[str, ...]
    entities: tuple[str, ...]
    approved_aliases: tuple[str, ...]
    exact_terms: tuple[str, ...]
    dates: tuple[str, ...]
    numbers: tuple[str, ...]
    metadata_filters: tuple[str, ...]
    negation_scope: str = Field(min_length=1, max_length=64)
    negation_confidence: float = Field(ge=0.0, le=1.0)
    document_scope: str = Field(min_length=1, max_length=256)
    section_scope: str = Field(min_length=1, max_length=256)
    page_scope: str = Field(min_length=1, max_length=64)
    media_intent: bool
    historical_relationship: bool
    low_confidence_relationship: bool
    relationship_intent: bool
    decomposition: tuple[str, ...] = Field(max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
    model_calls: Literal[0, 1]
    fallback_reason: str = Field(min_length=1, max_length=64)
    intent_fidelity: float = Field(ge=0.0, le=1.0)
    entity_fidelity: float = Field(ge=0.0, le=1.0)
    original_fallback_variant: str = Field(min_length=1, max_length=2000)
    query_type: str = Field(min_length=1, max_length=64)
    phase6_extension: Phase6Extension
    comparison: bool
    table_intent: bool
    corpus_wide_theme: bool
    whole_document_summary: bool
    routing_surface: RoutingSurface
    manual_mode: bool

    @model_validator(mode="after")
    def _original_preserved(self) -> QueryPreparation:
        """Reject original-query loss and a fourth subquestion.

        Returns:
            This preparation.

        Raises:
            ValueError: If the original is missing or decomposition is too long.
        """

        if self.original_fallback_variant != self.original:
            raise ValueError("original_query_loss")
        if len(self.decomposition) > SUBQUESTION_CEILING:
            raise ValueError("fourth_subquestion")
        return self


class BranchSpec(BaseModel):
    """One bounded retrieval branch that inherits packet 1 authorization.

    Attributes:
        branch_id: Stable id within the plan.
        kind: Direct invocation kind.
        family: Route family this branch contributes to.
        query_text: Original or focused subquestion. Never a hidden rewrite call.
        parallel_group: Independent group; scheduler caps concurrency at 2.
        hl_keywords: Precomputed profile keywords. Empty fails graph retrieve.
        ll_keywords: Precomputed profile keywords. Empty fails graph retrieve.
        table_plan: Declarative table plan when known.
        reuse_hybrid_ranked_ids: Candidate IDs reused on Combined escalation.
        graph_as_evidence: Always false. Graph prose is never evidence.
        max_graph_expansions: At most three global steering expansions.
        inherit_run_id: Branch must copy the admitted run id.
        inherit_reservation: Branch must copy the run-local reservation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    branch_id: str = Field(min_length=1, max_length=64)
    kind: BranchKind
    family: Phase6RouteFamily
    query_text: str = Field(min_length=1, max_length=2000)
    parallel_group: int = Field(ge=0, le=8)
    hl_keywords: tuple[str, ...] = ()
    ll_keywords: tuple[str, ...] = ()
    table_plan: TableQueryPlan | None = None
    reuse_hybrid_ranked_ids: tuple[str, ...] = ()
    graph_as_evidence: bool = False
    max_graph_expansions: int = Field(
        default=MAX_GRAPH_EXPANSIONS, ge=0, le=MAX_GRAPH_EXPANSIONS
    )
    inherit_run_id: bool = True
    inherit_reservation: bool = True

    @model_validator(mode="after")
    def _never_graph_evidence(self) -> BranchSpec:
        """Forbid treating graph prose as evidence.

        Returns:
            This spec.

        Raises:
            ValueError: If ``graph_as_evidence`` is true.
        """

        if self.graph_as_evidence:
            raise ValueError("graph_prose_never_evidence")
        return self


class RetrievalPlan(BaseModel):
    """Deterministic allow-listed plan. Client route is not authorization.

    Attributes:
        requested_route: Envelope family reserved at packet 1 admit.
        effective_route: Planner-selected family. May be cheaper, never larger.
        corrected_route: Family after the one correction, else None.
        branches: Required branches, at most three subquestions worth.
        limitations: Named limitation codes.
        historical_relationship: Past/as_of relationship stays Hybrid.
        temporal_graph_limitation: Graph retrieve is forbidden when true.
        whole_document_summary: Requires ``section_coverage_ratio=1.0``.
        section_coverage_required: Frozen whole-document ratio. Always 1.0.
        coverage_threshold: Frozen per-class threshold. Not retuned here.
        company_claim_forbidden: True for NoRetrieval.
        graph_as_answer_forbidden: True for graph-only inspection.
        prove_complement: Always false. Negation never proves a complement.
        media_answer_forbidden: True when media-only evidence is required.
        manual_mode: Diagnostic manual routing was recorded.
        routing_surface: Production or diagnostic.
        hybrid_prose_composition: Table branch may later compose Hybrid prose.
        relationship_signal_retained: Kept for possible Hybrid→Combined.
        fallback_reason: Envelope/graph/table limitation reason.
        branch_concurrency: Server cap, default 2.
        max_subquestions: Server cap, default 3.
        catalog_llm_call_count: Must stay 0.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_route: Phase6RouteFamily
    effective_route: Phase6RouteFamily
    corrected_route: Phase6RouteFamily | None = None
    branches: tuple[BranchSpec, ...]
    limitations: tuple[str, ...] = ()
    historical_relationship: bool = False
    temporal_graph_limitation: bool = False
    whole_document_summary: bool = False
    section_coverage_required: float = WHOLE_DOCUMENT_SECTION_COVERAGE
    coverage_threshold: float = PROVISIONAL_COVERAGE_THRESHOLD
    company_claim_forbidden: bool = False
    graph_as_answer_forbidden: bool = False
    prove_complement: bool = False
    media_answer_forbidden: bool = False
    manual_mode: bool = False
    routing_surface: RoutingSurface = RoutingSurface.PRODUCTION
    hybrid_prose_composition: bool = False
    relationship_signal_retained: bool = False
    fallback_reason: str | None = None
    branch_concurrency: int = Field(default=BRANCH_CONCURRENCY, ge=1, le=2)
    max_subquestions: int = Field(default=SUBQUESTION_CEILING, ge=1, le=3)
    catalog_llm_call_count: Literal[0] = 0

    @model_validator(mode="after")
    def _invariants(self) -> RetrievalPlan:
        """Reject unbounded fan-out, complement proof, and graph answers.

        Returns:
            This plan.

        Raises:
            ValueError: If a hard invariant is violated.
        """

        if self.prove_complement:
            raise ValueError("unproved_complement")
        if (
            self.effective_route is Phase6RouteFamily.NO_RETRIEVAL
            and not self.company_claim_forbidden
        ):
            raise ValueError("noretrieval_company_claim")
        if (
            self.effective_route is Phase6RouteFamily.GRAPH_INSPECTION
            and not self.graph_as_answer_forbidden
        ):
            raise ValueError("graph_only_answer")
        if self.branch_concurrency > BRANCH_CONCURRENCY:
            raise ValueError("branch_fan_out")
        if self.section_coverage_required != WHOLE_DOCUMENT_SECTION_COVERAGE:
            raise ValueError("holdout_driven_threshold_change")
        if (
            self.coverage_threshold != PROVISIONAL_COVERAGE_THRESHOLD
            and abs(self.coverage_threshold - PROVISIONAL_COVERAGE_THRESHOLD) > 1e-12
        ):
            raise ValueError("holdout_driven_threshold_change")
        return self


class TableEvidenceRecord(BaseModel):
    """Deterministic structured-table snapshot. Never model-calculated prose math.

    Attributes:
        table_id: Canonical table UUID string.
        version_id: Current version UUID string.
        document_id: Owning document UUID string.
        source_ranges: Exact cell or range provenance.
        operation: Aggregations and comparison summary.
        rows: JSON-safe result dictionaries.
        sheet: Sheet name.
        workbook: Workbook or CSV name.
        units: Result unit.
        from_prose: Must stay false. Prose arithmetic is forbidden.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    table_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    document_id: str = Field(min_length=1, max_length=36)
    source_ranges: tuple[str, ...] = ()
    operation: str = Field(min_length=1, max_length=256)
    rows: tuple[dict[str, object], ...] = ()
    sheet: str | None = None
    workbook: str | None = None
    units: str | None = None
    from_prose: Literal[False] = False


class BranchResult(BaseModel):
    """Retrieval outcome for one branch, including packet 3 evidence snapshots.

    Attributes:
        branch_id: Matching spec id.
        kind: Invocation kind.
        family: Family executed.
        run_id: Admitted run copied from packet 1 context.
        reservation_id: Run-local reservation copied from packet 1 context.
        query_text: Query used for this branch.
        ranked_ids: Canonical Hybrid IDs. Empty for non-Hybrid kinds.
        coverage_score: Hybrid coverage_score when computed.
        section_coverage_ratio: Whole-document heading ratio when applicable.
        uncovered_headings: Headings missing from bounded evidence.
        fallback_reason: Named retrieve/limitation reason.
        limitations: Graph or routing limitation codes.
        keyword_extract_count: Must stay 0. Hidden LightRAG extract is forbidden.
        catalog_llm_call_count: Must stay 0.
        acl_blindness_count: Authorized-only count, or None when suppressed.
        graph_survival_ratio: Resolver survival when a graph branch ran.
        bm25_snippets_used: Always false. Snippets are never evidence.
        graph_prose_used: Always false.
        company_claim: Always false on NoRetrieval.
        status: ``ok``, ``degraded``, ``refused``, or ``failed``.
        hybrid_evidence: Canonical Hybrid passages with post-rerank ranks.
        graph_paths: Resolved application paths. Native prose is forbidden.
        graph_passages: Canonical locators for graph chunk IDs.
        table_evidence: Deterministic table provenance when this is a table
            branch.
        graph_timeout: True when LightRAG missed its deadline.
        lightrag_answer_generate_count: Must stay 0.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    branch_id: str
    kind: BranchKind
    family: Phase6RouteFamily
    run_id: UUID
    reservation_id: UUID
    query_text: str
    ranked_ids: tuple[str, ...] = ()
    coverage_score: float | None = Field(default=None, ge=0.0, le=1.0)
    section_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    uncovered_headings: tuple[str, ...] = ()
    fallback_reason: str | None = None
    limitations: tuple[str, ...] = ()
    keyword_extract_count: Literal[0] = 0
    catalog_llm_call_count: Literal[0] = 0
    acl_blindness_count: int | None = Field(default=None, ge=0)
    graph_survival_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    bm25_snippets_used: Literal[False] = False
    graph_prose_used: Literal[False] = False
    company_claim: Literal[False] = False
    status: Literal["ok", "degraded", "refused", "failed"] = "ok"
    hybrid_evidence: tuple[HybridPassage, ...] = ()
    graph_paths: tuple[GraphPathInput, ...] = ()
    graph_passages: tuple[GraphPassage, ...] = ()
    table_evidence: TableEvidenceRecord | None = None
    graph_timeout: bool = False
    lightrag_answer_generate_count: Literal[0] = 0


class CorrectionDecision(BaseModel):
    """At most one global correction. Never a loop and never both kinds.

    Attributes:
        applied: Whether the single budget was spent.
        kind: Escalation, same-route retry, or none.
        reason: Machine-readable reason.
        routing_correction: Persist value ``hybrid_to_combined`` when used.
        remaining_corrections: Slots left after this decision (0 or 1).
        exhausted_status: ``insufficient_evidence`` when the budget is spent
            without enough coverage.
        already_applied: Guard against a second correction or loop.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    applied: bool
    kind: CorrectionKind
    reason: str
    routing_correction: str | None = None
    remaining_corrections: int = Field(ge=0, le=1)
    exhausted_status: str | None = None
    already_applied: bool = False


REQUIRED_PREPARATION_FIELDS: frozenset[str] = frozenset(QueryPreparation.model_fields)
