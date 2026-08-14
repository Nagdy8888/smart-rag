"""Immutable Phase 4 evaluation-case schema, versions, and label contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smart_rag_core.evaluation.classes import QueryClass, RuntimeOwner

DATASET_SCHEMA_VERSION = "phase4-dataset-v1"
LABEL_REVISION = "phase4-labels-synthetic-v1"
NORMALIZER_VERSION = "arabic_norm_v1"
DATE_PARSER_VERSION = "gregorian_v1"
PROFILE_PROMPT_PLACEHOLDER = "unspecified_until_packet_3"
PROFILE_MODEL_PLACEHOLDER = "unspecified_until_packet_3"
DEFAULT_RETRIEVAL_PROFILE_ID = "hybrid_default_v1"


class DatasetSplit(StrEnum):
    """Source-family-disjoint evaluation split."""

    DEVELOPMENT = "development"
    QUALIFICATION = "qualification"
    HOLDOUT = "holdout"


class FieldProvenance(StrEnum):
    """How a labeled profile field was obtained."""

    DETERMINISTIC = "deterministic"
    APPROVED_ALIAS = "approved_alias"
    MODEL_INFERRED = "model_inferred"
    USER_SUPPLIED = "user_supplied"


class AdjudicationStatus(StrEnum):
    """SME adjudication state. Disagreement is never silently gold-forced."""

    AGREED = "agreed"
    ALTERNATIVES_RETAINED = "alternatives_retained"
    DISAGREEMENT_OPEN = "disagreement_open"


class QueryType(StrEnum):
    """Labeled query-type values matching the Phase 4 profile contract."""

    EXACT_IDENTIFIER = "exact_identifier"
    FACTUAL = "factual"
    SEMANTIC_CONCEPTUAL = "semantic_conceptual"
    MULTI_PART = "multi_part"
    RELATIONSHIP_MULTI_HOP = "relationship_multi_hop"
    BROAD_SUMMARY = "broad_summary"
    STRUCTURED_TABULAR = "structured_tabular_aggregation"


class ExpectedRoute(StrEnum):
    """Labeled answering or refusal route. Later-phase routes stay labels."""

    HYBRID = "hybrid"
    COMBINED = "combined"
    STRUCTURED_TABLE = "structured_table"
    GRAPH_INSPECTION = "graph_inspection"
    REFUSAL = "refusal"


class RefusalKind(StrEnum):
    """Explicit no-answer or limitation truth."""

    NONE = "none"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONTRADICTORY_AUTHORITY = "contradictory_authority"
    ACL_FILTERED = "acl_filtered"
    MEDIA_LIMITATION = "media_limitation"
    SCOPED_SUMMARY = "scoped_summary"
    NEGATION_UNSCOPED = "negation_unscoped"


class FailureStage(StrEnum):
    """First-failing stage attribution placeholder until later packets score."""

    NONE = "none"
    PROFILE = "profile"
    CANDIDATE = "candidate"
    AUTHORIZATION = "authorization"
    FUSION = "fusion"
    RERANK = "rerank"
    CONTEXT = "context"
    COVERAGE = "coverage"
    TABLE = "table"
    DEFERRED_OWNER = "deferred_owner"


class ProfileField(BaseModel):
    """One labeled profile field with confidence and provenance.

    Attributes:
        value: Typed JSON-compatible field value.
        confidence: Closed unit interval.
        provenance: How the value was obtained.
        source_span: Optional query substring supporting the value.
        rule_id: Optional deterministic rule identifier.
        alias_id: Optional approved-alias identifier.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    value: str | int | float | bool | list[str] | None
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: FieldProvenance
    source_span: str | None = None
    rule_id: str | None = None
    alias_id: str | None = None


class AclActor(BaseModel):
    """ACL actor snapshot that retrieval must honor for the case.

    Attributes:
        actor_id: Stable synthetic actor identifier.
        role: Company role.
        authorization_snapshot_id: Versioned ACL snapshot identifier.
        restricted: Whether the actor is limited to restricted documents.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    actor_id: str = Field(min_length=3, max_length=64)
    role: Literal["owner", "admin", "member", "viewer"]
    authorization_snapshot_id: str = Field(min_length=3, max_length=64)
    restricted: bool = False


class EvidenceLink(BaseModel):
    """Atomic canonical evidence link or an explicit empty-evidence marker.

    Attributes:
        source_id: Synthetic canonical source identifier.
        version_id: Synthetic document version identifier.
        chunk_id: Passage identifier when text evidence exists.
        table_id: Table identifier when structured evidence exists.
        locator: Page/section/sheet/range coordinates.
        visible_to_actor: Whether the labeled actor may see this evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=3, max_length=64)
    version_id: str = Field(min_length=3, max_length=64)
    chunk_id: str | None = None
    table_id: str | None = None
    locator: dict[str, str] = Field(default_factory=dict)
    visible_to_actor: bool = True


class ExpectedProfile(BaseModel):
    """Complete expected query-profile labels for one case.

    Attributes:
        original_query: Unmodified query text.
        normalizer_version: Pinned Arabic/search normalizer version.
        date_parser_version: Pinned Gregorian date-parser version.
        prompt_version: Profile prompt placeholder until Packet 3.
        model_version: Profile model placeholder until Packet 3.
        language: Detected language field.
        locale_configuration: Mixed-locale/configuration field.
        query_type: Query-type field.
        exact_terms: Exact term list.
        quoted_phrases: Quoted phrase list.
        codes: Identifier/code list.
        numbers: Numeric literals.
        dates: Date literals.
        entities: Entity strings.
        approved_aliases: Approved alias strings.
        requested_sources: Requested document/source filters.
        metadata_filters: Allow-listed metadata filters.
        temporal_intent: Temporal intent enum text.
        target_date: Target date or null.
        timezone: Comparison timezone, UTC unless signed otherwise.
        authoritative_date_field: ``effective_at``, ``published_at``, or none.
        negation_scope: Negation/exclusion scope.
        document_scope: Document/section/page/sheet/range scope.
        media_dependence: Whether required evidence is figure-only.
        historical_relationship: Relationship intent anchored to a past date.
        relationship_intent: Relationship/multi-hop signal.
        table_intent: Structured-table signal.
        table_operation_hints: Allow-listed table operations.
        rewrite_justified: Whether variants are justified.
        subquestions: At most three decomposition strings.
        variants: At most three focused variants.
        hl_keywords: Precomputed high-level keywords.
        ll_keywords: Precomputed low-level keywords.
        retrieval_profile_id: Allow-listed retrieval profile identifier.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    original_query: str = Field(min_length=1, max_length=2000)
    normalizer_version: str = Field(min_length=1, max_length=64)
    date_parser_version: str = Field(min_length=1, max_length=64)
    prompt_version: str = Field(min_length=1, max_length=64)
    model_version: str = Field(min_length=1, max_length=64)
    language: ProfileField
    locale_configuration: ProfileField
    query_type: ProfileField
    exact_terms: ProfileField
    quoted_phrases: ProfileField
    codes: ProfileField
    numbers: ProfileField
    dates: ProfileField
    entities: ProfileField
    approved_aliases: ProfileField
    requested_sources: ProfileField
    metadata_filters: ProfileField
    temporal_intent: ProfileField
    target_date: ProfileField
    timezone: ProfileField
    authoritative_date_field: ProfileField
    negation_scope: ProfileField
    document_scope: ProfileField
    media_dependence: ProfileField
    historical_relationship: ProfileField
    relationship_intent: ProfileField
    table_intent: ProfileField
    table_operation_hints: ProfileField
    rewrite_justified: ProfileField
    subquestions: ProfileField
    variants: ProfileField
    hl_keywords: ProfileField
    ll_keywords: ProfileField
    retrieval_profile_id: ProfileField

    @field_validator("subquestions", "variants")
    @classmethod
    def _bound_lists(cls, field: ProfileField) -> ProfileField:
        """Reject more than three subquestions or variants.

        Args:
            field: Profile field whose value must be a short list or empty.

        Returns:
            The unchanged field when the list length is at most three.

        Raises:
            ValueError: If the value is a list longer than three items.
        """

        if isinstance(field.value, list) and len(field.value) > 3:
            raise ValueError("at most three subquestions or variants")
        return field


class EvaluationCase(BaseModel):
    """One labeled Phase 4 evaluation case.

    Attributes:
        case_id: Immutable case identifier.
        source_family_id: Family that must stay inside one split.
        query_class: Canonical class.
        split: Assigned split.
        schema_version: Dataset schema version.
        label_revision: Label revision identifier.
        query: Original query text.
        language: Query language code.
        acceptable_answers: Answer variants; empty when refusal is expected.
        evidence_links: Canonical evidence or empty for no-evidence truth.
        refusal_kind: Explicit refusal or limitation kind.
        expected_route: Labeled route.
        runtime_owner: Phase allowed to execute the case.
        acl_actor: Actor and authorization snapshot.
        expected_profile: Complete profile field labels.
        adjudication_status: SME adjudication state.
        adjudicators: Adjudicator identifiers.
        disagreement_notes: Preserved disagreement text; never a silent gold.
        first_failure_stage: Attribution placeholder.
        redaction_class: ``synthetic`` for this corpus.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=8, max_length=64, pattern=r"^p4-[a-z0-9_]+-\d{4}$")
    source_family_id: str = Field(min_length=8, max_length=64)
    query_class: QueryClass
    split: DatasetSplit
    schema_version: str = Field(min_length=1, max_length=64)
    label_revision: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "ar", "mixed"]
    acceptable_answers: list[str]
    evidence_links: list[EvidenceLink]
    refusal_kind: RefusalKind
    expected_route: ExpectedRoute
    runtime_owner: RuntimeOwner
    acl_actor: AclActor
    expected_profile: ExpectedProfile
    adjudication_status: AdjudicationStatus
    adjudicators: list[str] = Field(min_length=1)
    disagreement_notes: str | None = None
    first_failure_stage: FailureStage = FailureStage.NONE
    redaction_class: Literal["synthetic"] = "synthetic"

    @model_validator(mode="after")
    def _require_evidence_or_refusal(self) -> EvaluationCase:
        """Require evidence links or an explicit no-evidence refusal.

        Returns:
            The validated case.

        Raises:
            ValueError: If both evidence and refusal truth are missing, gold
                was forced on open disagreement, or a holdout case is unlabeled.
        """

        if not self.evidence_links and self.refusal_kind is RefusalKind.NONE:
            raise ValueError("case requires evidence links or explicit refusal truth")
        if (
            self.adjudication_status is AdjudicationStatus.DISAGREEMENT_OPEN
            and len(self.acceptable_answers) == 1
            and self.disagreement_notes is None
        ):
            raise ValueError("open disagreement cannot be forced to a single gold")
        if self.expected_profile.original_query != self.query:
            raise ValueError("profile original_query must equal query")
        return self


class SplitManifest(BaseModel):
    """Frozen ordered case identifiers and content hashes for one split.

    Attributes:
        schema_version: Dataset schema version.
        label_revision: Label revision.
        split: Split name.
        case_ids: Ordered case identifiers.
        source_family_ids: Ordered unique family identifiers.
        case_hashes: Mapping of case id to SHA-256 of canonical case JSON.
        manifest_hash: SHA-256 of the ordered ids and hashes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    label_revision: str
    split: DatasetSplit
    case_ids: list[str]
    source_family_ids: list[str]
    case_hashes: dict[str, str]
    manifest_hash: str = Field(min_length=64, max_length=64)


def det(
    value: str | int | float | bool | list[str] | None,
    *,
    span: str | None = None,
    rule_id: str | None = None,
    alias_id: str | None = None,
    provenance: FieldProvenance = FieldProvenance.DETERMINISTIC,
    confidence: float = 1.0,
) -> ProfileField:
    """Build a deterministic labeled profile field.

    Args:
        value: Field value.
        span: Optional supporting query span.
        rule_id: Optional rule identifier.
        alias_id: Optional alias identifier.
        provenance: Provenance enum.
        confidence: Closed unit interval.

    Returns:
        Frozen ``ProfileField``.
    """

    return ProfileField(
        value=value,
        confidence=confidence,
        provenance=provenance,
        source_span=span,
        rule_id=rule_id,
        alias_id=alias_id,
    )
