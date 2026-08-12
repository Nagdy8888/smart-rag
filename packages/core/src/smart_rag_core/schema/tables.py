"""Pydantic mirrors for key authoritative tables and shared job columns."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.schema.enums import (
    DocumentVisibility,
    JobErrorCategory,
    JobPriority,
    JobStatus,
    UserRole,
)

EMBEDDING_DIMENSIONS = 1024


class DurableJobColumns(BaseModel):
    """Shared lease/idempotency columns on every durable queue table."""

    model_config = ConfigDict(extra="forbid")

    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    idempotency_key: str
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=8, ge=1)
    next_attempt_at: datetime | None = None
    error_category: JobErrorCategory | None = None
    payload_ref: dict[str, Any] = Field(default_factory=dict)


class ProfileRecord(BaseModel):
    """Authoritative membership profile row."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: UserRole = UserRole.MEMBER
    display_name: str | None = None
    upload_enabled: bool = False
    mfa_enrolled: bool = False
    disabled_at: datetime | None = None
    session_revoked_at: datetime | None = None
    monthly_llm_budget_usd: float | None = None
    daily_ingestion_budget_usd: float | None = None
    upload_quota_bytes: int | None = None
    created_at: datetime
    updated_at: datetime


class CompanySettingsRecord(BaseModel):
    """Singleton company policy including authorization snapshot generation."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    company_name: str | None = None
    authorization_version: int = Field(default=1, ge=1)
    default_document_visibility: DocumentVisibility = DocumentVisibility.COMPANY_VISIBLE
    visibility_generation: int = Field(default=1, ge=1)
    monthly_llm_budget_usd: float | None = None
    daily_ingestion_budget_usd: float | None = None
    upload_quota_bytes: int | None = None
    quarantine_byte_cap: int | None = None
    timezone: str = "UTC"
    created_at: datetime
    updated_at: datetime


class DocumentRecord(BaseModel):
    """Canonical document shell with current-version pointer."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    description: str | None = None
    visibility: DocumentVisibility = DocumentVisibility.COMPANY_VISIBLE
    current_version_id: UUID | None = None
    visibility_generation: int = Field(default=1, ge=1)
    graph_eligible: bool = False
    created_by: UUID | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DocumentChunkRecord(BaseModel):
    """Hybrid canonical passage with pinned embedding dimension."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: UUID
    version_id: UUID
    chunk_index: int = Field(ge=0)
    raw_text: str
    search_normalized: str | None = None
    embedding: list[float] | None = Field(
        default=None, min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS
    )
    token_count: int | None = None
    page_number: int | None = None
    section_path: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    parent_chunk_id: UUID | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IngestionJobRecord(DurableJobColumns):
    """Durable ingestion queue row."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: UUID | None = None
    version_id: UUID | None = None
    job_kind: str
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class AuditEventRecord(BaseModel):
    """Append-only audit ledger row."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    event_type: str
    actor_user_id: UUID | None = None
    actor_role: UserRole | None = None
    target_type: str | None = None
    target_id: UUID | None = None
    authorization_version: int | None = None
    visibility_generation: int | None = None
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
