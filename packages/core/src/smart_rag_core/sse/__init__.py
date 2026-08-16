"""Versioned SSE protocol: catalog, framing, handshake, and event stores."""

from smart_rag_core.sse.catalog import (
    ALLOWED_SSE_EVENT_TYPES,
    HEARTBEAT_INTERVAL_SECONDS,
    TERMINAL_SSE_EVENT_TYPES,
)
from smart_rag_core.sse.framing import (
    ParsedSseEvent,
    format_sse_event,
    iter_known_sse_events,
    parse_sse_frames,
)
from smart_rag_core.sse.handshake import client_version_is_supported, parse_semver_tuple
from smart_rag_core.sse.sanitize import (
    sanitize_error_payload,
    strip_forbidden_payload,
    validate_sse_payload,
)
from smart_rag_core.sse.store import (
    MemoryRunEventStore,
    PersistedRunEvent,
    PostgresRunEventStore,
    RunEventStore,
)

__all__ = [
    "ALLOWED_SSE_EVENT_TYPES",
    "HEARTBEAT_INTERVAL_SECONDS",
    "TERMINAL_SSE_EVENT_TYPES",
    "MemoryRunEventStore",
    "ParsedSseEvent",
    "PersistedRunEvent",
    "PostgresRunEventStore",
    "RunEventStore",
    "client_version_is_supported",
    "format_sse_event",
    "iter_known_sse_events",
    "parse_semver_tuple",
    "parse_sse_frames",
    "sanitize_error_payload",
    "strip_forbidden_payload",
    "validate_sse_payload",
]
