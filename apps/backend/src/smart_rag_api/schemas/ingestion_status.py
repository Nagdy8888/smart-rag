"""FastAPI schemas for ingestion status and safe retry actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IngestionStatusResponse(BaseModel):
    """Public lifecycle plus diagnostics for one document version."""

    version_id: UUID
    document_id: UUID
    status: str
    version_number: int
    is_current: bool
    retrieval_eligible: bool
    title: str
    visibility: str
    document_graph_eligible: bool
    visibility_generation: int
    chunk_count: int
    chunk_set_hash: str | None = None
    embedding_model: str | None = None
    embedding_policy_hash: str | None = None
    hybrid_verified_at: datetime | None = None
    bm25_verified_at: datetime | None = None
    graph_handoff_at: datetime | None = None
    embedding_ledger_count: int = 0
    bm25_jobs: dict[str, Any] = Field(default_factory=dict)
    graph_handoff_jobs: dict[str, Any] = Field(default_factory=dict)
    retry_allowed: bool = False


class IngestionJobSummary(BaseModel):
    """Safe ingestion job diagnostic row."""

    id: UUID
    job_kind: str
    status: str
    priority: str
    attempt_count: int
    max_attempts: int
    error_category: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentIngestionStatusResponse(BaseModel):
    """Document-scoped ingestion status envelope."""

    version: IngestionStatusResponse
    recent_jobs: list[IngestionJobSummary] = Field(default_factory=list)


class RetryIngestionJobResponse(BaseModel):
    """Result of a role-scoped dead-letter or failed-job retry."""

    job_id: UUID
    status: str
    detail: str
