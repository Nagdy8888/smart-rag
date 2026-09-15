"""Typed answer, citation, inference-link, and verifier contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smart_rag_core.query_answer.versions import (
    MAX_VERIFIER_LINKS,
    PARAGRAPH_DELIMITER,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.web_research.models import WebCitation


class AtomicLink(BaseModel):
    """One ordered atomic claim that must cite canonical evidence.

    Attributes:
        link_id: Stable id within the answer.
        claim: Atomic claim text.
        chunk_ids: Canonical passage IDs supporting this link.
        web_source_ids: Persisted Web source IDs when the answer is Web.
        table_id: Optional table UUID when the claim is a table value.
        source_ranges: Table cell/range provenance when ``table_id`` is set.
        kind: Fact link or multi-hop inference link.
        priority: Lower is more material for the verifier batch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    link_id: str = Field(min_length=1, max_length=64)
    claim: str = Field(min_length=1, max_length=2000)
    chunk_ids: tuple[str, ...] = ()
    web_source_ids: tuple[str, ...] = ()
    table_id: str | None = None
    source_ranges: tuple[str, ...] = ()
    kind: Literal["fact", "inference_link"] = "fact"
    priority: int = Field(default=100, ge=0, le=10_000)


class ComposedConclusion(BaseModel):
    """Multi-hop conclusion labeled inference. Need not appear verbatim.

    Attributes:
        text: Composed conclusion.
        kind: Always ``inference``.
        link_ids: Ordered atomic links that support the conclusion.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    kind: Literal["inference"] = "inference"
    link_ids: tuple[str, ...] = ()


class AnswerParagraph(BaseModel):
    """One grounded answer paragraph and the atomic links that support it.

    Attributes:
        paragraph_index: Contiguous zero-based index in ``0..5``.
        text: Paragraph body without an embedded blank-paragraph delimiter.
        link_ids: One to six atomic-link IDs required to support the prose.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    paragraph_index: int = Field(ge=0, le=5)
    text: str = Field(min_length=1, max_length=4000)
    link_ids: tuple[str, ...] = Field(min_length=1, max_length=6)

    @field_validator("text")
    @classmethod
    def _reject_embedded_delimiter(cls, value: str) -> str:
        """Reject paragraph bodies that already contain the join delimiter.

        Args:
            value: Candidate paragraph text.

        Returns:
            The validated text.

        Raises:
            ValueError: If the body contains ``PARAGRAPH_DELIMITER``.
        """

        if PARAGRAPH_DELIMITER in value:
            raise ValueError("paragraph_index_invalid")
        return value


class AnswerCitation(BaseModel):
    """One canonical citation span or table range.

    Attributes:
        chunk_id: Canonical chunk UUID when the evidence is a passage.
        table_id: Canonical table UUID when the evidence is a table value.
        span: Exact 1-1000 character substring of canonical citation text.
        source_ranges: Exact table ranges, when a table value.
        inference: True when this citation supports a composed inference.
        atomic_link_id: Owning atomic link.
        paragraph_index: Owning paragraph, or ``None`` on legacy payloads.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str | None = None
    table_id: str | None = None
    span: str | None = Field(default=None, max_length=1000)
    source_ranges: tuple[str, ...] = ()
    inference: bool = False
    atomic_link_id: str | None = None
    paragraph_index: int | None = Field(default=None, ge=0, le=5)


class AnswerPayload(BaseModel):
    """Structured answer generation result. Extra fields are forbidden.

    Attributes:
        answer_text: Grounded answer prose. Derived from ``paragraphs`` on
            live company answers; never trusted from the provider.
        paragraphs: Ordered company paragraphs. Empty on general/Web and
            legacy fixtures.
        citations: Canonical citations only.
        web_citations: Run-scoped Web citations. Empty on company answers.
        atomic_links: Ordered links. Each cites at least one source.
        composed_conclusion: Labeled inference, or None.
        table_citations: Deterministic table provenance.
        status: ``complete``, ``partial``, or ``refused``.
        refused_links: Link IDs omitted or refused as unsupported.
        answer_origin: Strict-split knowledge scope for newly generated
            answers. ``None`` for historical or unset payloads.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer_text: str = Field(default="", max_length=16_384)
    paragraphs: tuple[AnswerParagraph, ...] = ()
    citations: tuple[AnswerCitation, ...] = ()
    web_citations: tuple[WebCitation, ...] = ()
    atomic_links: tuple[AtomicLink, ...] = ()
    composed_conclusion: ComposedConclusion | None = None
    table_citations: tuple[AnswerCitation, ...] = ()
    status: Literal["complete", "partial", "refused"] = "complete"
    refused_links: tuple[str, ...] = ()
    answer_origin: KnowledgeScope | None = None


class VerifierLinkVerdict(BaseModel):
    """One verifier judgment for an atomic link.

    Attributes:
        link_id: Matching atomic link.
        supported: True only when the cited source contains the claim.
        reason: Short machine-readable reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    link_id: str = Field(min_length=1, max_length=64)
    supported: bool
    reason: str = Field(min_length=1, max_length=128)


class VerifierPayload(BaseModel):
    """Structured verifier batch. At most six link verdicts.

    Attributes:
        link_verdicts: Verdicts aligned with the submitted batch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    link_verdicts: tuple[VerifierLinkVerdict, ...] = Field(
        max_length=MAX_VERIFIER_LINKS
    )

    @model_validator(mode="after")
    def _cap(self) -> VerifierPayload:
        """Reject a seventh verdict in one payload.

        Returns:
            This payload.

        Raises:
            ValueError: If more than six verdicts are present.
        """

        if len(self.link_verdicts) > MAX_VERIFIER_LINKS:
            raise ValueError("verifier_batch_cap")
        return self


class TableComposition(BaseModel):
    """Separate table evidence type composed with Hybrid/Combined.

    Attributes:
        records: Deterministic sandbox results with exact provenance.
        from_prose: Must stay false.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    records: tuple[TableEvidenceRecord, ...] = ()
    from_prose: Literal[False] = False


class VerificationResult(BaseModel):
    """Layered verification outcome after deterministic checks and one call.

    Attributes:
        answer: Answer after unsupported-link removal.
        deterministic_failures: Reason codes from current/ACL/span checks.
        verifier_call_count: ``0`` or ``1``. Never 2.
        omitted_link_ids: Lower-priority links excluded from the batch.
        status: Terminal status. Never fake success.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: AnswerPayload
    deterministic_failures: tuple[str, ...] = ()
    verifier_call_count: Literal[0, 1] = 0
    omitted_link_ids: tuple[str, ...] = ()
    status: Literal["verified", "verified_partial", "refused", "insufficient_evidence"]
