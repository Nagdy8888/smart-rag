"""HTTP schemas for the hosted PDF evaluation case API. Extra fields forbidden."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from smart_rag_core.evaluation.private_pdf.schema import (
    WORKSPACE_MAX_ANSWER_CHARS,
    WORKSPACE_MAX_QUESTION_CHARS,
)


class PdfEvalStatusResponse(BaseModel):
    """Workspace status without questions or filesystem paths."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    schema_ready: bool = True
    holdout_opened: bool = False
    draft_count: int = Field(ge=0, le=60)
    approved_count: int = Field(ge=0, le=60)
    rejected_count: int = Field(ge=0, le=60)
    stale_gold_count: int = Field(ge=0, le=60)
    live_count: int = Field(ge=0, le=60)
    remaining_capacity: int = Field(ge=0, le=60)


class PdfEvalGoldLocatorResponse(BaseModel):
    """Server-derived gold locator."""

    model_config = ConfigDict(frozen=True)

    ordinal: int = Field(ge=1, le=3)
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    page_number: int | None = None
    page_label: str | None = None
    section_path: tuple[str, ...] = ()
    stale: bool = False


class PdfEvalCaseSummaryResponse(BaseModel):
    """List row without question, answer, facts, or excerpts."""

    model_config = ConfigDict(frozen=True)

    case_id: UUID
    split: str
    query_class: str
    review_status: str
    generated_only: bool
    source_family_id: str | None = None
    gold_chunk_count: int = Field(ge=0, le=3)
    gold_stale: bool = False
    row_version: int = Field(ge=1)
    human_approved: bool = False


class PdfEvalCaseListResponse(BaseModel):
    """Paginated summaries. Bulk question fields are omitted."""

    model_config = ConfigDict(frozen=True)

    items: list[PdfEvalCaseSummaryResponse]
    next_case_id: UUID | None = None


class PdfEvalCaseDetailResponse(BaseModel):
    """Owner/admin case detail including private question fields."""

    model_config = ConfigDict(frozen=True)

    case_id: UUID
    split: str
    query_class: str
    review_status: str
    generated_only: bool
    source_family_id: str | None = None
    question: str = Field(max_length=WORKSPACE_MAX_QUESTION_CHARS)
    expected_answer: str = Field(max_length=WORKSPACE_MAX_ANSWER_CHARS)
    atomic_facts: tuple[str, ...]
    required_terms: tuple[str, ...]
    expected_scope: str
    source_run_id: UUID | None = None
    document_id: UUID | None = None
    version_id: UUID | None = None
    gold: tuple[PdfEvalGoldLocatorResponse, ...]
    gold_stale: bool
    reviewer_user_id: UUID | None = None
    row_version: int = Field(ge=1)
    human_approved: bool = False


class PdfEvalCaseCreateRequest(BaseModel):
    """Create a draft from a caller-owned run. Browser question text is omitted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_run_id: UUID
    expected_answer: str = Field(default="", max_length=WORKSPACE_MAX_ANSWER_CHARS)
    atomic_facts: tuple[str, ...] = ()
    query_class: str
    required_terms: tuple[str, ...] = ()
    split: str = "development"
    source_family_id: str | None = Field(default=None, min_length=8, max_length=128)
    chunk_ids: tuple[UUID, ...] = ()
    idempotency_key: str = Field(min_length=8, max_length=128)


class PdfEvalCasePatchRequest(BaseModel):
    """Editable fields plus expected row_version. Extra forbid."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_row_version: int = Field(ge=1)
    question: str | None = Field(
        default=None, min_length=1, max_length=WORKSPACE_MAX_QUESTION_CHARS
    )
    expected_answer: str | None = Field(
        default=None, max_length=WORKSPACE_MAX_ANSWER_CHARS
    )
    atomic_facts: tuple[str, ...] | None = None
    query_class: str | None = None
    required_terms: tuple[str, ...] | None = None
    source_family_id: str | None = None
    expected_scope: str | None = None


class PdfEvalGoldReplaceRequest(BaseModel):
    """Replace gold chunk IDs. Locators are server-derived."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_row_version: int = Field(ge=1)
    chunk_ids: tuple[UUID, ...] = Field(default=(), max_length=3)


class PdfEvalRevisionRequest(BaseModel):
    """Compare-and-swap body for approve, reject, and delete."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_row_version: int = Field(ge=1)


class PdfEvalRegenerateRequest(BaseModel):
    """Regenerate generated-only drafts for one current document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: UUID


class PdfEvalMutationResponse(BaseModel):
    """New row version after a mutation."""

    model_config = ConfigDict(frozen=True)

    case_id: UUID | None = None
    row_version: int | None = None
    inserted_count: int | None = None
    gold_chunk_count: int | None = None
    replayed: bool | None = None


class PdfEvalPassageResponse(BaseModel):
    """Authorized current representative passage."""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    page_number: int | None = None
    heading_path: tuple[str, ...] = ()
    raw_text: str


class PdfEvalPassageListResponse(BaseModel):
    """Bounded passage page."""

    model_config = ConfigDict(frozen=True)

    items: list[PdfEvalPassageResponse]
    next_chunk_id: UUID | None = None


class PdfEvalReportResponse(BaseModel):
    """Count-only latest report. No questions or excerpts."""

    model_config = ConfigDict(frozen=True)

    present: bool
    holdout_opened: bool = False
    case_count: int | None = None
    gates_pass: bool | None = None
    hybrid_recall_at_10: float | None = None


class PdfEvalCompareRunRequest(BaseModel):
    """Compare an owned run's citations to gold chunk IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID


class PdfEvalCompareRunResponse(BaseModel):
    """Count-only citation overlap. Official Recall@10 stays the exam runner."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    split: str
    gold_count: int
    citation_count: int
    intersection: int
    ranked_hit_at_10: int
    run_id: UUID
    manual_ai_test: bool = True


class PdfEvalExamStartRequest(BaseModel):
    """Start or reconnect a production-corpus Hybrid exam."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    split: str = Field(pattern="^(development|qualification)$")
    idempotency_key: str = Field(min_length=8, max_length=128)
    expected_dataset_hash: str | None = Field(
        default=None, min_length=64, max_length=64
    )


class PdfEvalExamAcceptedResponse(BaseModel):
    """202 enqueue or idempotent reconnect. No hidden conversation id."""

    model_config = ConfigDict(frozen=True)

    exam_run_id: UUID
    status: str
    dataset_hash: str
    replayed: bool
    holdout_opened: bool = False


class PdfEvalExamStatusResponse(BaseModel):
    """Poll row without questions, ranked IDs, or gold UUID lists."""

    model_config = ConfigDict(frozen=True)

    exam_run_id: UUID
    split: str
    status: str
    dataset_hash: str
    case_count: int = Field(ge=0, le=60)
    completed_case_count: int = Field(ge=0, le=60)
    holdout_opened: bool = False
    candidate_fingerprint: str | None = None


class PdfEvalExamReportResponse(BaseModel):
    """Split-isolated latest official report. Partial runs never appear."""

    model_config = ConfigDict(frozen=True)

    present: bool
    holdout_opened: bool = False
    exam_run_id: UUID | None = None
    split: str | None = None
    dataset_hash: str | None = None
    case_count: int | None = None
    hit_count: int | None = None
    hybrid_recall_at_10: float | None = None
    gates_pass: bool | None = None
    created_at: datetime | None = None


class PdfEvalExamCaseResponse(BaseModel):
    """Count-only report case. ``hit=false`` is a missed case."""

    model_config = ConfigDict(frozen=True)

    case_id: UUID
    ordinal: int = Field(ge=1)
    hit: bool
    gold_count: int = Field(ge=1, le=3)
    ranked_hit_count: int = Field(ge=0, le=3)
    latency_ms: int | None = None


class PdfEvalExamCaseListResponse(BaseModel):
    """Report cases without questions or excerpts."""

    model_config = ConfigDict(frozen=True)

    exam_run_id: UUID
    items: list[PdfEvalExamCaseResponse]
    missed_count: int = Field(ge=0, le=60)
