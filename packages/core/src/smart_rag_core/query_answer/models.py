"""Typed answer, citation, inference-link, and verifier contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_rag_core.query_answer.versions import MAX_VERIFIER_LINKS
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord


class AtomicLink(BaseModel):
    """One ordered atomic claim that must cite canonical evidence.

    Attributes:
        link_id: Stable id within the answer.
        claim: Atomic claim text.
        chunk_ids: Canonical passage IDs supporting this link.
        table_id: Optional table UUID when the claim is a table value.
        source_ranges: Table cell/range provenance when ``table_id`` is set.
        kind: Fact link or multi-hop inference link.
        priority: Lower is more material for the verifier batch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    link_id: str = Field(min_length=1, max_length=64)
    claim: str = Field(min_length=1, max_length=2000)
    chunk_ids: tuple[str, ...] = ()
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


class AnswerCitation(BaseModel):
    """One canonical citation span or table range.

    Attributes:
        chunk_id: Canonical chunk UUID when the evidence is a passage.
        table_id: Canonical table UUID when the evidence is a table value.
        span: Substring of canonical citation text, when a passage.
        source_ranges: Exact table ranges, when a table value.
        inference: True when this citation supports a composed inference.
        atomic_link_id: Owning atomic link.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str | None = None
    table_id: str | None = None
    span: str | None = Field(default=None, max_length=4000)
    source_ranges: tuple[str, ...] = ()
    inference: bool = False
    atomic_link_id: str | None = None


class AnswerPayload(BaseModel):
    """Structured answer generation result. Extra fields are forbidden.

    Attributes:
        answer_text: Grounded answer prose.
        citations: Canonical citations only.
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
    citations: tuple[AnswerCitation, ...] = ()
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
