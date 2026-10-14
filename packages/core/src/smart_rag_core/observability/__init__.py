"""Shared observability primitives for Smart RAG deployables."""

from smart_rag_core.observability.error_telemetry import (
    configure_error_telemetry,
    flush_error_telemetry,
    scrub_glitchtip_event,
    telemetry_span,
)
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
    "configure_error_telemetry",
    "configure_json_logging",
    "configure_langsmith",
    "flush_error_telemetry",
    "scrub_glitchtip_event",
    "telemetry_span",
    "correlation_context",
    "current_correlation_ids",
    "redact_text",
    "traced_async_openai_client",
    "traced_embeddings_create",
    "traced_embeddings_create_async",
    "traced_openai_client",
]
