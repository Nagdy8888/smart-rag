"""Local private-file evaluation workspace models. No HTTP types."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_rag_core.evaluation.private_pdf.schema import (
    WORKSPACE_MAX_ANSWER_CHARS,
    WORKSPACE_MAX_CASES,
    WORKSPACE_MAX_FACT_CHARS,
    WORKSPACE_MAX_FACTS,
    WORKSPACE_MAX_GOLD_CHUNKS,
    WORKSPACE_MAX_QUESTION_CHARS,
    PrivatePdfLabeledCase,
)


class WorkspacePathRejected(ValueError):
    """Raised when a workspace path is outside the server-owned root."""


class WorkspaceRevisionConflict(ValueError):
    """Raised when a mutation's expected revision does not match disk."""


class WorkspaceBoundsError(ValueError):
    """Raised when a workspace dataset or case exceeds local bounds."""


class WorkspaceCaseSummary(BaseModel):
    """List row without question, answer, facts, or excerpt text.

    Attributes:
        case_id: Stable case identifier.
        split: development, qualification, or holdout.
        query_class: Overlay evaluation class.
        human_approved: Named-human approval flag.
        generated_only: True until a human inspects the row.
        reviewer: Named reviewer id, or None.
        expected_refusal: Whether gold is a refusal.
        gold_chunk_count: Number of gold chunk locators.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    split: str
    query_class: str
    human_approved: bool
    generated_only: bool
    reviewer: str | None = None
    expected_refusal: bool = False
    gold_chunk_count: int = Field(ge=0, le=WORKSPACE_MAX_GOLD_CHUNKS)


class WorkspaceCasePatch(BaseModel):
    """Editable fields a human may change. Approval flags are server-owned.

    Attributes:
        question: Replacement question. Never logged.
        expected_answer: Extractive expected answer. Never logged.
        atomic_facts: Supporting facts. Never logged.
        chunk_ids: Gold chunk locators.
        page_numbers: Page locators aligned with chunks when provided.
        heading_paths: Heading locators.
        required_terms: Coverage terms that must appear in gold locators.
        expected_scope: whole_document, section, or unscoped.
        expected_refusal: Refusal gold.
        query_class: Overlay class token.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

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

    @field_validator("atomic_facts")
    @classmethod
    def _bound_facts(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        """Reject oversized fact lists.

        Args:
            value: Optional facts.

        Returns:
            The facts.

        Raises:
            ValueError: Too many facts or a fact is too long.
        """

        if value is None:
            return value
        if len(value) > WORKSPACE_MAX_FACTS:
            raise ValueError("workspace_fact_count")
        if any(len(item) > WORKSPACE_MAX_FACT_CHARS for item in value):
            raise ValueError("workspace_fact_chars")
        return value

    @field_validator("chunk_ids")
    @classmethod
    def _bound_chunks(cls, value: tuple[UUID, ...] | None) -> tuple[UUID, ...] | None:
        """Reject more than three gold chunks.

        Args:
            value: Optional chunk ids.

        Returns:
            The ids.

        Raises:
            ValueError: Empty or oversized gold set.
        """

        if value is None:
            return value
        if not value or len(value) > WORKSPACE_MAX_GOLD_CHUNKS:
            raise ValueError("workspace_gold_chunks")
        return value


class WorkspaceSnapshot(BaseModel):
    """Loaded workspace dataset plus the SHA-256 revision of the file bytes.

    Attributes:
        revision: SHA-256 of canonical on-disk JSON.
        relative_path: Server-owned path relative to the workspace root.
        version_id: Current PDF version id when recorded.
        document_id: Document id when recorded.
        content_hash: PDF SHA-256 when recorded.
        cases: Labeled rows. Callers must not print private fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: str = Field(min_length=64, max_length=64)
    relative_path: str
    version_id: str | None = None
    document_id: str | None = None
    content_hash: str | None = None
    cases: tuple[PrivatePdfLabeledCase, ...] = Field(max_length=WORKSPACE_MAX_CASES)
