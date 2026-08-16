"""FastAPI schemas for owner/admin graph entity-rule curation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

EntityRuleStatus = Literal["suggested", "approved", "revoked"]
EntityRuleSource = Literal["admin", "feedback", "model"]
RelationLabelPolicy = Literal["directed", "symmetric"]
AliasScope = Literal["company", "synthetic_eval"]


class EntityRuleUpsertRequest(BaseModel):
    """Create or update one entity rule. Members cannot mutate rules."""

    entity_type: str = Field(min_length=1, max_length=64)
    canonical_name: str = Field(min_length=1, max_length=256)
    aliases: list[str] = Field(default_factory=list[str], max_length=32)
    do_not_merge: list[str] = Field(default_factory=list[str], max_length=32)
    display_label: str | None = Field(default=None, max_length=256)
    languages: list[str] = Field(default_factory=list[str], max_length=8)
    alias_scope: AliasScope = "company"
    relation_label_policy: RelationLabelPolicy = "directed"
    reason: str = Field(default="", max_length=512)
    source: EntityRuleSource = "admin"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: EntityRuleStatus = "approved"
    row_version: int | None = Field(default=None, ge=1)


class EntityRuleSuggestRequest(BaseModel):
    """Inactive feedback or model candidate. Approval is a separate action."""

    entity_type: str = Field(min_length=1, max_length=64)
    canonical_name: str = Field(min_length=1, max_length=256)
    aliases: list[str] = Field(default_factory=list[str], max_length=32)
    do_not_merge: list[str] = Field(default_factory=list[str], max_length=32)
    display_label: str | None = Field(default=None, max_length=256)
    languages: list[str] = Field(default_factory=list[str], max_length=8)
    alias_scope: AliasScope = "company"
    relation_label_policy: RelationLabelPolicy = "directed"
    reason: str = Field(default="", max_length=512)
    source: EntityRuleSource = "feedback"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class EntityRuleConcurrencyRequest(BaseModel):
    """Optimistic concurrency token for approve or revoke."""

    row_version: int = Field(ge=1)


class EntityRuleMutationResponse(BaseModel):
    """Identifiers after a rule mutation. Alias text is omitted."""

    rule_id: UUID
    status: EntityRuleStatus
    row_version: int
    entity_rules_generation: int
    rebuild_job_id: UUID | None = None
    repair_job_id: UUID | None = None
    invalidated: bool = False


class EntityRuleListItem(BaseModel):
    """One rule row for owner/admin listing."""

    id: UUID
    entity_type: str
    canonical_name: str | None
    display_label: str | None
    aliases: tuple[str, ...]
    do_not_merge: tuple[str, ...]
    languages: tuple[str, ...]
    alias_scope: str
    relation_label_policy: str
    status: EntityRuleStatus
    active: bool
    row_version: int
    source: EntityRuleSource
    reason: str
    confidence: float | None
    created_at: datetime | None
    updated_at: datetime | None


class EntityRuleListResponse(BaseModel):
    """Owner/admin listing of curated and suggested rules."""

    rules: tuple[EntityRuleListItem, ...]
