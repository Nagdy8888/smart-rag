"""In-memory table artifact bundle."""

from __future__ import annotations

from pydantic import BaseModel

from smart_rag_core.ingestion.tables.limits import TABLE_ARTIFACT_BUCKET
from smart_rag_core.ingestion.tables.manifest import TableArtifactManifest


class TableArtifactBundle(BaseModel):
    """In-memory table artifact ready for Storage upload."""

    manifest: TableArtifactManifest
    parquet_bytes: bytes
    bucket: str = TABLE_ARTIFACT_BUCKET
