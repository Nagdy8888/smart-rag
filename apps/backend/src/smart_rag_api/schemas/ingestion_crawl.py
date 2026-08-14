"""FastAPI schemas for approved website crawl enqueue."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class EnqueueWebsiteCrawlRequest(BaseModel):
    """Owner/admin request to crawl one approved start URL."""

    start_url: str = Field(min_length=8, max_length=2048)
    approved_domain: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=256)
    document_title: str | None = Field(default=None, max_length=512)
    max_depth: int = Field(default=2, ge=1, le=5)
    max_pages: int = Field(default=50, ge=1, le=200)
    content_class: str = Field(default="synthetic", max_length=32)
    graph_eligible: bool = False
    attestation_policy_version: str | None = Field(default=None, max_length=128)


class EnqueueWebsiteCrawlResponse(BaseModel):
    """Identifiers created or reused for one approved crawl enqueue."""

    document_id: UUID
    version_id: UUID
    source_id: UUID
    approval_id: UUID
    job_id: UUID
