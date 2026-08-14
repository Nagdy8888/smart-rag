"""Runtime query-profile result and optional structured model payload."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.query_profile.versions import MAX_SUBQUESTIONS, MAX_VARIANTS


class ProfileFallbackReason(StrEnum):
    """Typed safe routes when the optional profile model cannot be used."""

    NONE = "none"
    NOT_NEEDED = "not_needed"
    TIMEOUT = "profile_timeout"
    REFUSAL = "profile_refusal"
    MALFORMED = "profile_malformed"
    BUDGET_DENIED = "profile_budget_denied"
    UNKNOWN_FIELD = "unknown_hard_field"


class ModelInferredProfile(BaseModel):
    """Optional inferred fields from one structured profile call.

    Attributes:
        query_type: Optional inferred type. Deterministic type wins on conflict.
        subquestions: At most three strings.
        variants: At most three strings.
        retrieval_profile_id: Must be allow-listed when present.
        confidence: Closed unit interval for inferred filters/type.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_type: str | None = None
    subquestions: list[str] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)
    retrieval_profile_id: str | None = None
    metadata_filters: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("subquestions", "variants")
    @classmethod
    def _cap_lists(cls, value: list[str]) -> list[str]:
        """Reject more than three subquestions or variants.

        Args:
            value: Candidate list.

        Returns:
            The list when it is within bounds.

        Raises:
            ValueError: If the list is longer than three items.
        """

        if len(value) > MAX_SUBQUESTIONS or len(value) > MAX_VARIANTS:
            raise ValueError("at most three subquestions or variants")
        return value


class QueryProfileResult(BaseModel):
    """Complete profiler output for one query.

    Attributes:
        profile: Typed profile matching the evaluation field contract.
        model_calls: ``0`` or ``1``. A second hidden call is forbidden.
        fallback_reason: Safe route when the model is skipped or rejected.
        diagnostics: Soft unknown-filter or fidelity messages.
        prompt_sha256: Hash of the versioned prompt file.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ExpectedProfile
    model_calls: int = Field(ge=0, le=1)
    fallback_reason: ProfileFallbackReason
    diagnostics: tuple[str, ...] = ()
    prompt_sha256: str = Field(min_length=64, max_length=64)
