"""Route enums, branch specs, and the frozen retrieval plan."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    MAX_GRAPH_EXPANSIONS,
    PROVISIONAL_COVERAGE_THRESHOLD,
    SUBQUESTION_CEILING,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    NoRetrievalAnswerMode,
    ScopeDegradationReason,
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
        knowledge_scope: Strict-split answer origin copied from preparation.
        no_retrieval_answer_mode: Required for NoRetrieval; None for company
            document routes.
        scope_degradation_reason: Server-derived failed-inference reason
            copied from preparation. Distinct from ``fallback_reason``.
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
    knowledge_scope: KnowledgeScope
    no_retrieval_answer_mode: NoRetrievalAnswerMode | None = None
    scope_degradation_reason: ScopeDegradationReason | None = None

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
        if (
            self.scope_degradation_reason is not None
            and self.knowledge_scope is not KnowledgeScope.GENERAL_KNOWLEDGE
        ):
            raise ValueError("scope_degradation_scope_mismatch")
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
