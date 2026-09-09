"""Frozen contracts for the isolated PDF parser bake-off."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.evaluation.parser_bakeoff.constants import (
    ANYDOC_LANE,
    CURRENT_LANE,
    SCHEMA_VERSION,
    LaneId,
)


class BakeoffError(RuntimeError):
    """Fail-closed bake-off error with a stable machine code."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize with a sanitized operator detail.

        Args:
            code: Stable machine code.
            detail: Operator-safe detail without source text or secrets.
        """

        super().__init__(detail)
        self.code = code
        self.detail = detail


class RunStage(StrEnum):
    """Resumable bake-off stage tokens."""

    PREPARED = "prepared"
    PARSED = "parsed"
    INDEXED = "indexed"
    MAPPED = "mapped"
    GOLD_VALIDATED = "gold_validated"
    EVALUATED = "evaluated"
    REPORTED = "reported"


class MappingStatus(StrEnum):
    """Atomic-fact mapping outcome for one lane."""

    AUTOMATIC = "automatic"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNMAPPED = "unmapped"


class Classification(StrEnum):
    """Final bake-off recommendation token."""

    CURRENT_PRIMARY = "current_primary"
    ANYDOC_SECONDARY_CANDIDATE = "anydoc_secondary_candidate"
    ANYDOC_PRIMARY_CANDIDATE = "anydoc_primary_candidate"
    INCONCLUSIVE = "inconclusive"


class BakeoffScanEvidence(BaseModel):
    """Count-only ClamAV evidence stored in the run manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    disposition: str
    engine_version: str
    signature_version: str
    signature_db_ids: dict[str, str] = Field(default_factory=dict)
    bytes_examined: int = Field(ge=0)
    detail: str = ""


class LaneIdentity(BaseModel):
    """Parser identity recorded per lane."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane_id: LaneId
    parser_version: str
    cleaning_version: str
    config_hash: str = ""
    locator_available: bool
    ingest_document_id: UUID | None = None
    ingest_version_id: UUID | None = None
    bm25_job_id: UUID | None = None


class BakeoffManifest(BaseModel):
    """Immutable run metadata. Never stores source text or credentials."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    source_basename: str
    source_sha256: str
    source_bytes: int = Field(ge=0)
    source_pages: int = Field(ge=0)
    scan: BakeoffScanEvidence
    lanes: tuple[LaneIdentity, ...]
    stage: RunStage = RunStage.PREPARED
    command_version: str
    created_at: str
    content_class: Literal["real_company"] = "real_company"
    graph_eligible: Literal[False] = False
    holdout_opened: Literal[False] = False
    source_text_emitted: Literal[False] = False
    secrets_emitted: Literal[False] = False
    generalization_claim: Literal[False] = False
    embedding_model: str = ""
    chat_model: str = ""
    retrieval_profile_id: str = ""
    retrieval_profile_digest: str = ""
    chunking_version: str = ""
    protocol_frozen: bool = False
    experimental_only: bool = True
    actor_id: str | None = None
    manifest_sha256: str = ""


class NeutralCase(BaseModel):
    """Parser-neutral sealed evaluation case without chunk UUIDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    split: str
    source_family_id: str
    query_class: str
    question: str
    expected_answer: str = ""
    atomic_facts: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    page_numbers: tuple[int, ...] = ()
    expected_refusal: bool = False
    expected_profile_id: str = "hybrid_default_v1"
    expected_scope: str = "unscoped"
    acl_actor_id: str | None = None
    human_approved: bool = False
    reviewer: str | None = None


class NeutralCaseSet(BaseModel):
    """Sealed parser-neutral case file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    source_sha256: str
    original_seal_sha256: str
    split: str
    holdout_opened: Literal[False] = False
    cases: tuple[NeutralCase, ...]
    case_set_sha256: str = ""


class GoldMappingItem(BaseModel):
    """One atomic-fact mapping into a lane's chunks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    fact_index: int = Field(ge=0)
    status: MappingStatus
    chunk_ids: tuple[UUID, ...] = ()
    candidate_chunk_ids: tuple[UUID, ...] = ()
    extraction_failure: bool = False


class GoldMap(BaseModel):
    """Approved or pending gold map for one lane."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane_id: LaneId
    source_sha256: str
    version_id: UUID
    reviewer: str | None = None
    approved: bool = False
    items: tuple[GoldMappingItem, ...]
    gold_map_sha256: str = ""


class ChunkSummary(BaseModel):
    """Count-only parse and chunk summary. No passage text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane_id: LaneId
    disposition: str
    failure_code: str | None = None
    parser_version: str
    cleaning_version: str
    config_hash: str
    chunking_config_hash: str = ""
    wall_seconds: float = Field(ge=0.0)
    peak_memory_mb: float | None = None
    pages_processed: int | None = None
    ocr_pages: int | None = None
    locator_available: bool
    element_kind_counts: dict[str, int] = Field(default_factory=dict)
    extracted_chars: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    passage_count: int = Field(ge=0)
    parent_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    ordinary_prose_in_target: int = Field(ge=0)
    ordinary_prose_chunks: int = Field(ge=0)
    exact_duplicate_groups: int = Field(ge=0)
    near_duplicate_pairs: int = Field(ge=0)
    chunks_with_locator: int = Field(ge=0)
    chunks_with_pdf_page: int = Field(ge=0)
    locator_chunk_ratio: float = Field(ge=0.0, le=1.0)
    pdf_page_chunk_ratio: float = Field(ge=0.0, le=1.0)
    token_band_counts: dict[str, int] = Field(default_factory=dict)
    replay_matched: bool = False
    element_text_hash: str = ""


class LaneIngestIds(BaseModel):
    """Document/version identifiers created for one bake-off lane."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane_id: LaneId
    document_id: UUID
    version_id: UUID
    title: str
    bm25_job_id: UUID | None = None
    status: str = "parsing"
    hybrid_ready: bool = False
    chunk_count: int = Field(ge=0, default=0)
    graph_eligible: Literal[False] = False
    content_class: Literal["real_company"] = "real_company"
    visibility: Literal["restricted"] = "restricted"


class CleanupReceipt(BaseModel):
    """Count-only cleanup outcome. Never lists unrelated IDs as deleted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    manifest_sha256: str
    documents_deleted: int = Field(ge=0)
    versions_deleted: int = Field(ge=0)
    chunks_remaining: int = Field(ge=0)
    bm25_rows_remaining: int = Field(ge=0)
    reports_deleted: bool = False
    idempotent: bool = True


class LaneRetrieveScore(BaseModel):
    """Per-case retrieval score without question text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    recall_hit_at_10: bool | None
    exact_hit_at_5: bool | None = None
    alias_hit_at_10: bool | None = None
    reciprocal_rank: float | None = None
    locator_ok: bool
    locator_available: bool
    refusal_ok: bool
    first_evidence_ms: float | None = None
    bm25_fallback: str = "none"
    rerank_call_count: int = Field(default=0, ge=0)
    ranked_id_count: int = Field(default=0, ge=0)
    cross_lane_leaks: int = Field(default=0, ge=0)
    acl_leak: bool = False


class LaneAgentScore(BaseModel):
    """Per-case answer/judge score without answer text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    citation_correctness: float
    citation_completeness: float
    fact_completeness: float
    faithfulness: float | None
    judge_status: str
    refusal_ok: bool
    invented_or_forbidden: int = Field(default=0, ge=0)
    answer_calls: int = Field(default=0, ge=0)
    judge_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = None
    budget_or_deadline_failed: bool = False


class PairedMetric(BaseModel):
    """One paired metric with bootstrap interval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    current: float | None
    anydoc_local: float | None
    delta: float | None
    ci_low: float | None
    ci_high: float | None
    winner: Literal["current", "anydoc_local", "tie", "unavailable"]


class ComparisonReport(BaseModel):
    """Git-safe side-by-side bake-off report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    source_sha256: str
    source_basename: str
    current: LaneIdentity
    anydoc_local: LaneIdentity
    current_chunk: ChunkSummary | None = None
    anydoc_chunk: ChunkSummary | None = None
    paired_metrics: tuple[PairedMetric, ...] = ()
    classification: Classification
    classification_reasons: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    unscored_count: int = Field(ge=0)
    mapping_review_count: int = Field(ge=0)
    acl_leaks: int = Field(ge=0)
    current_cost_usd: float | None = None
    anydoc_cost_usd: float | None = None
    bootstrap_seed: int = 20260909
    holdout_opened: Literal[False] = False
    source_text_emitted: Literal[False] = False
    secrets_emitted: Literal[False] = False
    generalization_claim: Literal[False] = False
    experimental_only: bool = True
    current_lane_name: Literal["current"] = CURRENT_LANE
    anydoc_lane_name: Literal["anydoc_local"] = ANYDOC_LANE
