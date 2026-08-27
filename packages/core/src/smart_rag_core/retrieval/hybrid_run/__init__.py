"""Hybrid retrieve package and compatibility re-exports."""

import psycopg

from smart_rag_core.retrieval.hybrid_run.channels import flatten_channel_candidates
from smart_rag_core.retrieval.hybrid_run.retriever import HybridRetriever
from smart_rag_core.retrieval.hybrid_run.types import (
    EvidenceLocator,
    EvidenceUnit,
    HybridRunResult,
)

__all__ = [
    "EvidenceLocator",
    "EvidenceUnit",
    "HybridRetriever",
    "HybridRunResult",
    "flatten_channel_candidates",
    "psycopg",
]
