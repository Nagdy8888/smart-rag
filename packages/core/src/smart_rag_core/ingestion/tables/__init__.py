"""Typed Parquet table artifact package.

Only the bundle type is eager so ``chunking.types`` can import it without
pulling Storage/gateway/embedding cycles through ``tables.service``.
Import ``build_table_artifacts`` from ``smart_rag_core.ingestion.tables.service``.
"""

from smart_rag_core.ingestion.tables.bundle import TableArtifactBundle

__all__ = ["TableArtifactBundle"]
