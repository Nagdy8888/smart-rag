"""Typed Parquet table artifact package."""

from smart_rag_core.ingestion.tables.bundle import TableArtifactBundle
from smart_rag_core.ingestion.tables.service import build_table_artifacts

__all__ = ["TableArtifactBundle", "build_table_artifacts"]
