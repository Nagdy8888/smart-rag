"""Private PDF evaluation dataset identity, distinct from the synthetic corpus."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

PRIVATE_PDF_SCHEMA_VERSION = "private-pdf-eval-v1"
PRIVATE_PDF_DATASET_ID = "private_pdf_book_v1"
PRIVATE_PDF_DATASET_VERSION = "v1"
MINIMUM_SEALED_CASES = 50
TARGET_SEALED_CASES = 60
WORKSPACE_MAX_CASES = 60
WORKSPACE_MAX_QUESTION_CHARS = 2_000
WORKSPACE_MAX_ANSWER_CHARS = 8_000
WORKSPACE_MAX_FACTS = 16
WORKSPACE_MAX_FACT_CHARS = 1_000
WORKSPACE_MAX_GOLD_CHUNKS = 3


class SealStatus(StrEnum):
    """Human review state for one private-PDF case."""

    DRAFT = "generated_draft"
    HUMAN_APPROVED = "human_approved"
    REJECTED = "rejected"


class PrivatePdfQueryClass(StrEnum):
    """Query classes for the one-PDF overlay dataset."""

    FACTUAL_DEFINITION = "factual_definition"
    EXACT_ACRONYM = "exact_acronym"
    SEMANTIC_PARAPHRASE = "semantic_paraphrase"
    MULTI_PART = "multi_part"
    SECTION_SCOPED = "section_scoped"
    FULL_SUMMARY_REFUSAL = "full_summary_refusal"
    INSUFFICIENT_OR_INJECTION = "insufficient_or_injection"


PRIVATE_PDF_CLASS_MINIMUMS: dict[PrivatePdfQueryClass, int] = {
    PrivatePdfQueryClass.FACTUAL_DEFINITION: 15,
    PrivatePdfQueryClass.EXACT_ACRONYM: 8,
    PrivatePdfQueryClass.SEMANTIC_PARAPHRASE: 8,
    PrivatePdfQueryClass.MULTI_PART: 6,
    PrivatePdfQueryClass.SECTION_SCOPED: 5,
    PrivatePdfQueryClass.FULL_SUMMARY_REFUSAL: 4,
    PrivatePdfQueryClass.INSUFFICIENT_OR_INJECTION: 4,
}


class PrivatePdfCase(BaseModel):
    """One source-grounded private-PDF evaluation case.

    Attributes:
        case_id: Deterministic id from hashes, never a question string.
        split: development, qualification, or holdout.
        source_family_id: Document hash plus chapter/section family.
        query_class: Overlay evaluation class.
        chunk_ids: Current authorized chunk UUIDs.
        page_numbers: Page locators.
        heading_paths: Heading locators. Private drafts may store paths;
            Git fixtures must keep them empty or synthetic.
        required_terms: Exact terms or approved aliases for coverage.
        expected_profile_id: Expected frozen profile after Packet 14.
        expected_scope: whole_document, section, or unscoped.
        expected_refusal: True for summary/injection/insufficient gold.
        acl_actor_id: Principal that must be able to read the version.
        human_approved: Named reviewer must set true before sealing.
        generated_only: True when the row was never inspected by a human.
        reviewer: Named human reviewer. Required to seal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=8, max_length=128)
    split: str
    source_family_id: str = Field(min_length=8, max_length=128)
    query_class: str
    chunk_ids: tuple[UUID, ...] = ()
    page_numbers: tuple[int, ...] = ()
    heading_paths: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    expected_profile_id: str = "hybrid_default_v1"
    expected_scope: str = "unscoped"
    expected_refusal: bool = False
    acl_actor_id: str | None = None
    human_approved: bool = False
    generated_only: bool = True
    reviewer: str | None = None

    @field_validator("split")
    @classmethod
    def _allow_splits(cls, value: str) -> str:
        """Reject unknown splits.

        Args:
            value: Split name.

        Returns:
            The split name.

        Raises:
            ValueError: Unknown split.
        """

        if value not in {"development", "qualification", "holdout"}:
            raise ValueError("unknown_private_pdf_split")
        return value

    @field_validator("query_class")
    @classmethod
    def _allow_query_class(cls, value: str) -> str:
        """Reject unknown overlay query classes.

        Args:
            value: Query class token.

        Returns:
            The class token.

        Raises:
            ValueError: Unknown class.
        """

        allowed = {item.value for item in PrivatePdfQueryClass}
        if value not in allowed:
            raise ValueError("unknown_private_pdf_query_class")
        return value


class PrivatePdfLabeledCase(BaseModel):
    """Gitignored labeled case. Question and answer never belong in Git.

    Attributes:
        meta: Git-safe locators and seal flags.
        question: Private question text. Callers must not print it.
        expected_answer: Expected answer or empty for refusals.
        atomic_facts: Atomic supporting facts. Never logged.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    meta: PrivatePdfCase
    question: str = Field(min_length=1)
    expected_answer: str = ""
    atomic_facts: tuple[str, ...] = ()
