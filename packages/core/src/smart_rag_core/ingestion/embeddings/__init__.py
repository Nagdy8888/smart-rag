"""Governed embedding generation and durable operation ledger."""

from smart_rag_core.ingestion.embeddings.contextual import (
    build_contextual_embedding_text,
)
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    embedding_policy_hash,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL",
    "build_contextual_embedding_text",
    "embedding_policy_hash",
]
