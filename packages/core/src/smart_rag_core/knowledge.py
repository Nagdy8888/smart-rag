"""Document authority contracts; labels never grant evidence access."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuthorityStatus(StrEnum):
    """Human-managed authority, independent of ingestion readiness."""

    UNREVIEWED = "unreviewed"
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class KnowledgeResult(BaseModel):
    """Final checked knowledge outcome, independent of operational failures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: Literal[
        "supported", "partial", "insufficient_evidence", "conflicting_evidence"
    ]
    limitations: tuple[str, ...] = Field(default=(), max_length=12)
    unanswered_parts: tuple[str, ...] = Field(default=(), max_length=3)


MaintenanceKind = Literal[
    "missing_owner",
    "overdue_review",
    "feedback",
    "insufficient_evidence",
    "conflicting_evidence",
]


class MaintenanceItem(BaseModel):
    """One currently authorized review task; reports require explicit consent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: MaintenanceKind
    source_id: UUID
    document_id: UUID | None = None
    run_id: UUID | None = None
    title: str | None = None
    report: dict[str, str | None] = Field(default_factory=dict)
    status: Literal["open", "resolved", "dismissed"] = "open"
    assigned_to: UUID | None = None
    reason: str | None = None
    revision: int = Field(default=0, ge=0)


class MaintenanceUpdate(BaseModel):
    """Optimistic human review, with a reason required for closing an item."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    expected_revision: int = Field(ge=0)
    status: Literal["open", "resolved", "dismissed"] = "open"
    assigned_to: UUID | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_closing_reason(self) -> MaintenanceUpdate:
        """Closing a knowledge issue must leave a reviewable explanation."""
        if self.status != "open" and not self.reason:
            raise ValueError("closing_reason_required")
        return self


class ConversationKnowledgeScope(BaseModel):
    """An owned conversation's selected document, rechecked on every run."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    document_id: UUID | None = None
    title: str | None = None
    unavailable: bool = False
    enabled: bool = False


class UpdateKnowledgeScope(BaseModel):
    """A null selection explicitly clears scope to authorized company documents."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    document_id: UUID | None = None


class DocumentGovernance(BaseModel):
    """Authorized metadata for one canonical version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version_id: UUID | None = None
    version_number: int | None = None
    owner_user_id: UUID | None = None
    owner_display_name: str | None = None
    knowledge_area: str | None = Field(default=None, max_length=120)
    review_due_at: date | None = None
    authority_status: AuthorityStatus = AuthorityStatus.UNREVIEWED
    effective_at: datetime | None = None
    superseded_by_version_id: UUID | None = None
    governance_generation: int = Field(default=1, ge=1)
    reliability_enabled: bool = False

    def warnings(self, *, today: date | None = None) -> tuple[str, ...]:
        """Return factual metadata warnings without guessing currentness."""
        day = today or datetime.now(UTC).date()
        warnings: list[str] = []
        if self.authority_status is AuthorityStatus.UNREVIEWED:
            warnings.append("source_unreviewed")
        if self.owner_user_id is None:
            warnings.append("source_owner_missing")
        if self.review_due_at is not None and self.review_due_at < day:
            warnings.append("source_review_overdue")
        return tuple(warnings)


class UpdateDocumentGovernance(BaseModel):
    """Full replacement of governance fields for an expected version."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    version_id: UUID
    expected_generation: int = Field(ge=1)
    owner_user_id: UUID | None = None
    knowledge_area: str | None = Field(default=None, min_length=1, max_length=120)
    review_due_at: date | None = None
    authority_status: AuthorityStatus = AuthorityStatus.UNREVIEWED
    effective_at: datetime | None = None
    superseded_by_version_id: UUID | None = None

    @model_validator(mode="after")
    def validate_authority(self) -> UpdateDocumentGovernance:
        """Reject ambiguous approval, naive dates, and invalid replacement links."""
        if self.effective_at is not None and self.effective_at.tzinfo is None:
            raise ValueError("effective_at_requires_timezone")
        if self.authority_status is AuthorityStatus.APPROVED:
            if self.owner_user_id is None or self.effective_at is None:
                raise ValueError("approval_requires_owner_and_effective_date")
        if self.authority_status is AuthorityStatus.SUPERSEDED:
            if self.superseded_by_version_id is None:
                raise ValueError("supersession_requires_replacement")
        elif self.superseded_by_version_id is not None:
            raise ValueError("replacement_requires_superseded_status")
        if self.superseded_by_version_id == self.version_id:
            raise ValueError("self_supersession_forbidden")
        return self
