"""FastAPI schemas for ingestion status and safe retry actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScanDiagnostics(BaseModel):
    """Latest append-only scan evidence for one version.

    Orthogonal to public lifecycle; never introduces a new status enum.
    """

    result: str | None = None
    evidence_id: UUID | None = None
    scanned_at: datetime | None = None
    age_seconds: float | None = None
    engine_version: str | None = None
    signature_version: str | None = None
    object_hash: str | None = None


class ReviewFindingSummary(BaseModel):
    """Role-safe detector finding identity. No matched secrets."""

    finding_id: UUID
    family: str
    bounded_count: int = 0
    scope: str | None = None
    detector_policy_version: str | None = None


class ReviewDiagnostics(BaseModel):
    """Category attestation plus detector-finding review diagnostics."""

    declared_category: str | None = None
    source_type: str | None = None
    approval_status: str | None = None
    attestation_policy_version: str | None = None
    finding_count: int = 0
    unresolved_family_count: int = 0
    findings: list[ReviewFindingSummary] = Field(
        default_factory=list[ReviewFindingSummary]
    )


class OcrDiagnostics(BaseModel):
    """Page and OCR counts derived from canonical chunks."""

    page_count: int = 0
    ocr_pages: int = 0


class ChunkTableDiagnostics(BaseModel):
    """Canonical chunk and structured-table counts."""

    chunk_count: int = 0
    table_count: int = 0


class EmbeddingDiagnostics(BaseModel):
    """Durable embedding ledger counts and policy identity."""

    ledger_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    model: str | None = None
    policy_hash: str | None = None


class Bm25Diagnostics(BaseModel):
    """BM25 projection index version, lag, retry, and dead-letter counts."""

    active_index_version: int | None = None
    index_schema_version: str | None = None
    lag_seconds: float | None = None
    pending: int = 0
    processing: int = 0
    failed: int = 0
    dead_letter: int = 0
    retry_attempts: int = 0
    verified_at: datetime | None = None


class QueueAgeDiagnostics(BaseModel):
    """Oldest pending ingestion job age for this version."""

    oldest_pending_job_age_seconds: float | None = None
    oldest_pending_job_kind: str | None = None


class GraphHandoffDiagnostics(BaseModel):
    """LightRAG index-job handoff counts (Phase 3 stops at Graph Pending)."""

    pending: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    dead_letter: int = 0


class IngestionStatusResponse(BaseModel):
    """Public lifecycle plus nested diagnostics for one document version."""

    model_config = ConfigDict(extra="ignore")

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
    scan: ScanDiagnostics = Field(default_factory=ScanDiagnostics)
    review: ReviewDiagnostics = Field(default_factory=ReviewDiagnostics)
    ocr: OcrDiagnostics = Field(default_factory=OcrDiagnostics)
    chunks_tables: ChunkTableDiagnostics = Field(default_factory=ChunkTableDiagnostics)
    embedding: EmbeddingDiagnostics = Field(default_factory=EmbeddingDiagnostics)
    bm25: Bm25Diagnostics = Field(default_factory=Bm25Diagnostics)
    queue_age: QueueAgeDiagnostics = Field(default_factory=QueueAgeDiagnostics)
    graph_handoff: GraphHandoffDiagnostics = Field(
        default_factory=GraphHandoffDiagnostics
    )
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
    recent_jobs: list[IngestionJobSummary] = Field(default_factory=lambda: [])


class RetryIngestionJobResponse(BaseModel):
    """Result of a role-scoped dead-letter or failed-job retry."""

    job_id: UUID
    status: str
    detail: str
