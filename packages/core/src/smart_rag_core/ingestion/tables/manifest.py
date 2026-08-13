"""Table artifact manifest contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from smart_rag_core.ingestion.tables.limits import TABLE_ARTIFACT_SCHEMA_VERSION


class ColumnManifest(BaseModel):
    """One logical column in a typed table artifact."""

    column_name: str
    original_header: str
    header_ordinal: int = Field(ge=0)
    column_type: str
    hidden: bool = False
    unit: str | None = None
    currency: str | None = None


class TableArtifactManifest(BaseModel):
    """Manifest describing one Parquet artifact and its provenance."""

    schema_version: str = TABLE_ARTIFACT_SCHEMA_VERSION
    table_name: str
    sheet_name: str | None = None
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    columns: tuple[ColumnManifest, ...] = Field(default_factory=tuple)
    parquet_path: str
    content_hash_sha256: str
    byte_size: int = Field(ge=0)
    parser_version: str
    cleaning_version: str
    source_format: str
    provenance: dict[str, Any] = Field(default_factory=dict)

    def manifest_hash(self) -> str:
        """Return deterministic manifest digest for linkage checks."""

        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
