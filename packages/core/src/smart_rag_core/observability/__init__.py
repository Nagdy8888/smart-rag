"""Shared observability primitives for Smart RAG deployables."""

from smart_rag_core.observability.langsmith_tracing import (
    configure_langsmith,
    traced_async_openai_client,
    traced_embeddings_create,
    traced_embeddings_create_async,
    traced_openai_client,
)
from smart_rag_core.observability.logging import (
    JsonLogFormatter,
    configure_json_logging,
    correlation_context,
    current_correlation_ids,
    redact_text,
)

__all__ = [
    "JsonLogFormatter",
    "configure_json_logging",
    "configure_langsmith",
    "correlation_context",
    "current_correlation_ids",
    "redact_text",
    "traced_async_openai_client",
    "traced_embeddings_create",
    "traced_embeddings_create_async",
    "traced_openai_client",
]
