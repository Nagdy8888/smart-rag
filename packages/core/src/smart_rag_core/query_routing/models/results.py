"""Branch, table, and correction result contracts."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.query_fusion.models import (
    GraphPassage,
    GraphPathInput,
    HybridPassage,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.models.plan import BranchKind, CorrectionKind


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
        alternate_query: Measured retry query when ``same_route_retry``.
            None for Combined escalation or skipped correction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    applied: bool
    kind: CorrectionKind
    reason: str
    routing_correction: str | None = None
    remaining_corrections: int = Field(ge=0, le=1)
    exhausted_status: str | None = None
    already_applied: bool = False
    alternate_query: str | None = Field(default=None, max_length=2000)
