"""Canonical ingestion persistence."""

from smart_rag_core.ingestion.canonical.repository import (
    CanonicalRepository,
    CanonicalWriteError,
)

__all__ = ["CanonicalRepository", "CanonicalWriteError"]
