"""HTTP schemas for the local PDF evaluation workspace. Extra fields forbidden."""

from __future__ import annotations

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
    case_count: int = Field(ge=0, le=60)
    revision: str | None = None
    version_id: str | None = None
    document_id: str | None = None
    dataset_present: bool = False


class PdfEvalCaseSummaryResponse(BaseModel):
    """List row without question, answer, facts, or excerpts."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    split: str
    query_class: str
    human_approved: bool
    generated_only: bool
    reviewer: str | None = None
    expected_refusal: bool = False
    gold_chunk_count: int = Field(ge=0, le=3)


class PdfEvalCaseListResponse(BaseModel):
    """Paginated summaries. Bulk question fields are omitted."""

    model_config = ConfigDict(frozen=True)

    revision: str
    items: list[PdfEvalCaseSummaryResponse]
    next_case_id: str | None = None


class PdfEvalCaseDetailResponse(BaseModel):
    """Owner/admin case detail including private question fields."""

    model_config = ConfigDict(frozen=True)

    revision: str
    case_id: str
    split: str
    query_class: str
    human_approved: bool
    generated_only: bool
    reviewer: str | None = None
    expected_refusal: bool
    expected_scope: str
    chunk_ids: tuple[UUID, ...]
    page_numbers: tuple[int, ...]
    heading_paths: tuple[str, ...]
    required_terms: tuple[str, ...]
    question: str = Field(max_length=WORKSPACE_MAX_QUESTION_CHARS)
    expected_answer: str = Field(max_length=WORKSPACE_MAX_ANSWER_CHARS)
    atomic_facts: tuple[str, ...]


class PdfEvalCasePatchRequest(BaseModel):
    """Editable fields plus the expected SHA-256 revision. Extra forbid."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_revision: str = Field(min_length=64, max_length=64)
    question: str | None = Field(
        default=None, min_length=1, max_length=WORKSPACE_MAX_QUESTION_CHARS
    )
    expected_answer: str | None = Field(
        default=None, max_length=WORKSPACE_MAX_ANSWER_CHARS
    )
    atomic_facts: tuple[str, ...] | None = None
    chunk_ids: tuple[UUID, ...] | None = None
    page_numbers: tuple[int, ...] | None = None
    heading_paths: tuple[str, ...] | None = None
    required_terms: tuple[str, ...] | None = None
    expected_scope: str | None = None
    expected_refusal: bool | None = None
    query_class: str | None = None


class PdfEvalRevisionRequest(BaseModel):
    """Compare-and-swap body for approve, reject, and regenerate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_revision: str | None = Field(default=None, min_length=64, max_length=64)


class PdfEvalMutationResponse(BaseModel):
    """New revision after a mutation."""

    model_config = ConfigDict(frozen=True)

    revision: str
    case_id: str | None = None


class PdfEvalPassageResponse(BaseModel):
    """Authorized current representative passage. Cross-document IDs omitted."""

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
    """Count-only citation overlap. Official Recall@10 stays CLI."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    split: str
    gold_count: int
    citation_count: int
    intersection: int
    ranked_hit_at_10: int
    run_id: UUID
    manual_ai_test: bool = True
