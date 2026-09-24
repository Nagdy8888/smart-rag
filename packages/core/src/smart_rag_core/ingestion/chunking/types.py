"""Chunking result contracts and provenance models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from smart_rag_core.ingestion.tables.bundle import TableArtifactBundle


class ChunkKind(StrEnum):
    """Supported canonical chunk roles."""

    PASSAGE = "passage"
    PARENT = "parent"


class ChunkProvenance(BaseModel):
    """Structured provenance for citations and reconstruction.

    ``search_exclusion_reason`` explains a chunk that is stored but is not a
    search representative for a reason other than deduplication. It is
    ``None`` for representatives and for duplicates, which carry
    ``CanonicalChunk.duplicate_of_chunk_id`` instead. ``"navigation_page"``
    marks a contents or index chunk excluded by
    ``smart_rag_core.ingestion.chunking.navigation``. The value is stored in
    the ``provenance`` JSONB column, so no migration is needed; rows written
    before this field have no key and read as ``None``.
    """

    element_ids: tuple[str, ...] = Field(default_factory=tuple)
    atomic_element_id: str | None = None
    fragment_ordinal: int = Field(default=0, ge=0)
    is_fragment: bool = False
    is_atomic_exception: bool = False
    locators: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    heading_ancestry: tuple[str, ...] = Field(default_factory=tuple)
    child_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)
    duplicate_locators: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    parser_version: str
    cleaning_version: str
    chunking_version: str
    tokenizer_version: str
    dedup_policy_version: str
    dedup_mode: str = "exact_and_near"
    normalized_content_hash: str
    search_exclusion_reason: str | None = None


class CanonicalChunk(BaseModel):
    """One hierarchical passage or parent chunk before persistence.

    ``is_search_representative`` is False for two reasons. An exact
    duplicate sets ``duplicate_of_chunk_id`` to the kept chunk. A navigation
    page leaves ``duplicate_of_chunk_id`` as ``None`` and sets
    ``provenance.search_exclusion_reason`` to ``"navigation_page"``. A
    non-representative stays stored with its locators but is not embedded,
    projected to BM25, given search terms, or returned by retrieval.
    """

    chunk_id: UUID
    chunk_index: int = Field(ge=0)
    kind: ChunkKind
    raw_text: str
    token_count: int = Field(ge=0)
    section_path: list[str] = Field(default_factory=list)
    parent_chunk_id: UUID | None = None
    page_number: int | None = None
    provenance: ChunkProvenance
    duplicate_of_chunk_id: UUID | None = None
    is_search_representative: bool = True


class DedupMetrics(BaseModel):
    """Measured duplicate detection metrics for one version."""

    exact_duplicate_groups: int = Field(default=0, ge=0)
    near_duplicate_pairs: int = Field(default=0, ge=0)
    fuzzy_enabled: bool = True
    fuzzy_precision: float | None = None
    fuzzy_recall: float | None = None
    dedup_mode: str = "exact_and_near"


class ChunkingMetrics(BaseModel):
    """Aggregate sizing and coverage metrics for one chunking run."""

    total_chunks: int = Field(default=0, ge=0)
    passage_chunks: int = Field(default=0, ge=0)
    parent_chunks: int = Field(default=0, ge=0)
    ordinary_prose_chunks: int = Field(default=0, ge=0)
    ordinary_prose_in_target: int = Field(default=0, ge=0)
    overlap_violations: int = Field(default=0, ge=0)
    hard_cap_violations: int = Field(default=0, ge=0)
    atomic_exceptions: int = Field(default=0, ge=0)
    dedup: DedupMetrics = Field(default_factory=DedupMetrics)


class ChunkingResult(BaseModel):
    """Closed chunking output for one parsed document version."""

    chunks: tuple[CanonicalChunk, ...] = Field(default_factory=tuple)
    table_artifacts: tuple[TableArtifactBundle, ...] = Field(default_factory=tuple)
    metrics: ChunkingMetrics = Field(default_factory=ChunkingMetrics)
    config_hash: str
