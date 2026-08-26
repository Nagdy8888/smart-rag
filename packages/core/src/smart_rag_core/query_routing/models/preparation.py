"""Preparation-facing memory, model payload, and query preparation types."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.query_routing.constants import SUBQUESTION_CEILING
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    ScopeDegradationReason,
)
from smart_rag_core.query_routing.models.plan import Phase6Extension, RoutingSurface


class MemoryRecord(BaseModel):
    """One untrusted conversation message loaded for preparation.

    Attributes:
        message_id: Canonical message UUID string.
        role: ``user``, ``assistant``, ``system``, or ``tool``.
        content: Truncated message text. Never a source document.
        created_at: ISO-8601 timestamp from Postgres.
        delimited: Instruction-safe delimited record for model input.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str = Field(min_length=1, max_length=36)
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(max_length=1500)
    created_at: str = Field(min_length=1, max_length=64)
    delimited: str = Field(min_length=1, max_length=2048)


class PreparationModelPayload(BaseModel):
    """One structured rewrite-plus-profile payload. Extra fields are forbidden.

    Attributes:
        rewrite: Optional standalone rewrite. Original remains the fallback.
        query_type: Optional inferred Phase 4 query type.
        subquestions: At most three strings.
        variants: At most three strings.
        hl_keywords: Precomputed high-level keywords. Never extracted later.
        ll_keywords: Precomputed low-level keywords. Never extracted later.
        retrieval_profile_id: Allow-listed Hybrid profile id when present.
        metadata_filters: Allow-listed filters.
        confidence: Closed unit interval.
        relationship_intent: Optional relationship signal from the model.
        knowledge_scope: Additive scope classification. Invalid values are
            ignored by ``classify_knowledge_scope``.
        knowledge_scope_confidence: Optional scope confidence from the same
            call. Values below 0.80 degrade to general knowledge.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rewrite: str | None = Field(default=None, max_length=2000)
    query_type: str | None = Field(default=None, max_length=64)
    subquestions: tuple[str, ...] = Field(default_factory=tuple, max_length=3)
    variants: tuple[str, ...] = Field(default_factory=tuple, max_length=3)
    hl_keywords: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    ll_keywords: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    retrieval_profile_id: str | None = Field(default=None, max_length=64)
    metadata_filters: tuple[str, ...] = Field(default_factory=tuple, max_length=8)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    relationship_intent: bool | None = None
    knowledge_scope: str | None = Field(default=None, max_length=64)
    knowledge_scope_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _bound_lists(self) -> PreparationModelPayload:
        """Reject a fourth subquestion or variant.

        Returns:
            This payload.

        Raises:
            ValueError: If more than three subquestions or variants appear.
        """

        if len(self.subquestions) > SUBQUESTION_CEILING:
            raise ValueError("fourth_subquestion")
        if len(self.variants) > SUBQUESTION_CEILING:
            raise ValueError("fourth_subquestion")
        return self


class QueryPreparation(BaseModel):
    """One typed preparation result. Every packet-2 field is required.

    Attributes:
        original: Unmodified user query. Always preserved.
        rewrite: Optional displayed rewrite. None when unused.
        profile: Frozen Phase 4 ``ExpectedProfile``.
        language: ``en``, ``ar``, or ``mixed``.
        temporal_intent: UTC-anchored temporal intent.
        timezone: ``UTC`` unless QUALITY_TARGETS signs another zone.
        hl_keywords: Precomputed high-level keywords.
        ll_keywords: Precomputed low-level keywords.
        entities: Entity strings.
        approved_aliases: Approved alias strings.
        exact_terms: Exact term list.
        dates: Date literals.
        numbers: Numeric literals.
        metadata_filters: Allow-listed filters.
        negation_scope: Negation enum.
        negation_confidence: Confidence for the negation scope.
        document_scope: Document/section/page scope text.
        section_scope: Section scope or ``none``.
        page_scope: Page scope or ``none``.
        media_intent: Figure/chart/diagram-only signal.
        historical_relationship: Past/as_of relationship signal.
        low_confidence_relationship: Ambiguous relationship kept for correction.
        relationship_intent: Relationship/multi-hop signal.
        decomposition: At most three subquestions.
        confidence: Overall preparation confidence.
        model_calls: ``0`` or ``1``. A second rewrite call is forbidden.
        fallback_reason: Profile/routing fallback code.
        intent_fidelity: Rewrite intent score against the original.
        entity_fidelity: Rewrite entity/code/alias score against the original.
        original_fallback_variant: Always the original query.
        query_type: Frozen Phase 4 query type string.
        phase6_extension: ``graph_inspection``, ``no_retrieval``, or ``none``.
        comparison: Whether this is a comparison subset of multi-part.
        table_intent: Structured-table signal.
        corpus_wide_theme: Corpus landscape/theme signal.
        whole_document_summary: Single-document full summary request.
        routing_surface: Production or diagnostic.
        manual_mode: True only when diagnostic manual routing was recorded.
        knowledge_scope: Strict-split answer origin.
        knowledge_scope_confidence: Confidence for ``knowledge_scope``.
        scope_degradation_reason: Server-derived failed-inference reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    original: str = Field(min_length=1, max_length=2000)
    rewrite: str | None = Field(default=None, max_length=2000)
    profile: ExpectedProfile
    language: str = Field(min_length=2, max_length=16)
    temporal_intent: str = Field(min_length=1, max_length=32)
    timezone: str = Field(min_length=1, max_length=64)
    hl_keywords: tuple[str, ...]
    ll_keywords: tuple[str, ...]
    entities: tuple[str, ...]
    approved_aliases: tuple[str, ...]
    exact_terms: tuple[str, ...]
    dates: tuple[str, ...]
    numbers: tuple[str, ...]
    metadata_filters: tuple[str, ...]
    negation_scope: str = Field(min_length=1, max_length=64)
    negation_confidence: float = Field(ge=0.0, le=1.0)
    document_scope: str = Field(min_length=1, max_length=256)
    section_scope: str = Field(min_length=1, max_length=256)
    page_scope: str = Field(min_length=1, max_length=64)
    media_intent: bool
    historical_relationship: bool
    low_confidence_relationship: bool
    relationship_intent: bool
    decomposition: tuple[str, ...] = Field(max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
    model_calls: Literal[0, 1]
    fallback_reason: str = Field(min_length=1, max_length=64)
    intent_fidelity: float = Field(ge=0.0, le=1.0)
    entity_fidelity: float = Field(ge=0.0, le=1.0)
    original_fallback_variant: str = Field(min_length=1, max_length=2000)
    query_type: str = Field(min_length=1, max_length=64)
    phase6_extension: Phase6Extension
    comparison: bool
    table_intent: bool
    corpus_wide_theme: bool
    whole_document_summary: bool
    routing_surface: RoutingSurface
    manual_mode: bool
    knowledge_scope: KnowledgeScope
    knowledge_scope_confidence: float = Field(ge=0.0, le=1.0)
    scope_degradation_reason: ScopeDegradationReason | None = None

    @model_validator(mode="after")
    def _original_preserved(self) -> QueryPreparation:
        """Reject original-query loss and a fourth subquestion.

        Returns:
            This preparation.

        Raises:
            ValueError: If the original is missing or decomposition is too long.
        """

        if self.original_fallback_variant != self.original:
            raise ValueError("original_query_loss")
        if len(self.decomposition) > SUBQUESTION_CEILING:
            raise ValueError("fourth_subquestion")
        if (
            self.scope_degradation_reason is not None
            and self.knowledge_scope is not KnowledgeScope.GENERAL_KNOWLEDGE
        ):
            raise ValueError("scope_degradation_scope_mismatch")
        return self


REQUIRED_PREPARATION_FIELDS: frozenset[str] = frozenset(QueryPreparation.model_fields)
