"""Branch, table, and correction result contracts."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_rag_core.query_fusion.models import (
    GraphPassage,
    GraphPathInput,
    HybridPassage,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.models.plan import BranchKind, CorrectionKind
from smart_rag_core.retrieval.profiles import (
    HYBRID_STAGE_TIMING_KEYS,
    RERANK_INVALID_SUBCODES,
)


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


class HybridBranchDiagnostics(BaseModel):
    """ID-only Hybrid retrieve diagnostics persisted on ``BranchResult``.

    Attributes:
        source_resolution: ``unscoped``, ``exact_one``, or ``ambiguous``.
        retrieval_profile_id: Frozen profile id actually executed.
        fallback_reason: Named retrieve fallback, or ``none``.
        rerank_fallback: Named rerank skip/failure, or ``none``.
        rerank_call_count: ``0`` or ``1``.
        embedding_call_count: ``0`` or ``1``.
        first_evidence_ms: Wall milliseconds to evidence or fail-closed.
        dense_ids: Authorized dense IDs, capped at 100.
        bm25_ids: Authorized BM25 IDs, capped at 75.
        term_ids: Authorized term IDs, capped at 30.
        fused_ids: Authorized fused IDs, capped at 100.
        selected_ids: Final evidence IDs, capped at 12.
        rerank_pool_ids: Chunk IDs that entered the one-shot rerank pool,
            in pool order, capped at 100.
        coverage_score: Frozen min() coverage when computed.
        term_coverage: Required-term component.
        subquestion_coverage: Subquestion component.
        evidence_ratio: Distinct-evidence component.
        support_confidence: Bounded support feature.
        effective_route: Executed branch family, never ``runs.route_family``.
        stage_timings_ms: ID-free wall-clock milliseconds per retrieve
            stage. Keys come from ``HYBRID_STAGE_TIMING_KEYS``; values are
            non-negative integers. Empty for older checkpoints.
        rerank_invalid_subcode: Rerank validation sub-code (``json``,
            ``hash``, ``length``, ``duplicate``, ``unknown_id``) when
            ``rerank_fallback`` is ``rerank_schema_invalid``, else empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_resolution: str = Field(min_length=1, max_length=32)
    retrieval_profile_id: str = Field(min_length=1, max_length=64)
    fallback_reason: str = Field(min_length=1, max_length=64)
    rerank_fallback: str = Field(min_length=1, max_length=64)
    rerank_call_count: int = Field(ge=0, le=1)
    embedding_call_count: int = Field(ge=0, le=1)
    first_evidence_ms: float = Field(ge=0.0)
    dense_ids: tuple[str, ...] = Field(default=(), max_length=100)
    bm25_ids: tuple[str, ...] = Field(default=(), max_length=75)
    term_ids: tuple[str, ...] = Field(default=(), max_length=30)
    fused_ids: tuple[str, ...] = Field(default=(), max_length=100)
    selected_ids: tuple[str, ...] = Field(default=(), max_length=12)
    rerank_pool_ids: tuple[str, ...] = Field(default=(), max_length=100)
    coverage_score: float | None = Field(default=None, ge=0.0, le=1.0)
    term_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    subquestion_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    support_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_route: str = Field(min_length=1, max_length=64)
    stage_timings_ms: dict[str, int] = Field(default_factory=dict[str, int])
    rerank_invalid_subcode: str = Field(default="", max_length=16)

    @field_validator(
        "dense_ids",
        "bm25_ids",
        "term_ids",
        "fused_ids",
        "selected_ids",
        "rerank_pool_ids",
    )
    @classmethod
    def ids_are_uuid_strings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject non-UUID diagnostic identifiers.

        Args:
            value: Candidate ID strings.

        Returns:
            The same tuple when every item is a UUID.

        Raises:
            ValueError: When an item is not a UUID string.
        """

        for item in value:
            UUID(item)
        return value

    @field_validator("stage_timings_ms")
    @classmethod
    def timings_are_known_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        """Reject unknown stage names and negative durations.

        Args:
            value: Stage name to integer milliseconds.

        Returns:
            The same mapping when every key is allow-listed and every
            value is at least zero.

        Raises:
            ValueError: ``stage_timing_key_invalid`` or
                ``stage_timing_negative``.
        """

        for key, item in value.items():
            if key not in HYBRID_STAGE_TIMING_KEYS:
                raise ValueError("stage_timing_key_invalid")
            if item < 0:
                raise ValueError("stage_timing_negative")
        return value

    @field_validator("rerank_invalid_subcode")
    @classmethod
    def subcode_is_known(cls, value: str) -> str:
        """Reject free-text rerank validation sub-codes.

        Args:
            value: Empty or one ``RERANK_INVALID_SUBCODES`` value.

        Returns:
            The same string.

        Raises:
            ValueError: ``rerank_subcode_invalid``.
        """

        if value and value not in RERANK_INVALID_SUBCODES:
            raise ValueError("rerank_subcode_invalid")
        return value


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
        hybrid_diagnostics: Optional ID-only Hybrid stage snapshot.
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
    hybrid_diagnostics: HybridBranchDiagnostics | None = None


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
