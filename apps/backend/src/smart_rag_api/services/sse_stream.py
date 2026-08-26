"""Compatibility facade for query SSE attach, heartbeat, and executors."""

from __future__ import annotations

import psycopg
from smart_rag_core.query_admission.service import true_up_query_reservation

from smart_rag_api.services.sse.chunks import (
    coerce_stream_token_count,
    token_counts_from_update,
    updates_mapping_from_chunk,
)
from smart_rag_api.services.sse.constants import CANCEL_GRACE_SECONDS
from smart_rag_api.services.sse.executors import (
    FixtureQueryRunExecutor,
    LangGraphQueryRunExecutor,
    QueryRunExecutor,
)
from smart_rag_api.services.sse.http import (
    SSE_RESPONSE_HEADERS,
    default_executor_factory,
    resume_after_sequence,
    sse_streaming_response,
    wants_event_stream,
)
from smart_rag_api.services.sse.registry import LiveQueryRun, QueryRunRegistry
from smart_rag_api.services.sse.service import SseStreamService

# Historical private names kept for existing monkeypatches and tests.
_coerce_stream_token_count = coerce_stream_token_count
_updates_mapping_from_chunk = updates_mapping_from_chunk
_token_counts_from_update = token_counts_from_update

__all__ = [
    "CANCEL_GRACE_SECONDS",
    "SSE_RESPONSE_HEADERS",
    "FixtureQueryRunExecutor",
    "LangGraphQueryRunExecutor",
    "LiveQueryRun",
    "QueryRunExecutor",
    "QueryRunRegistry",
    "SseStreamService",
    "default_executor_factory",
    "psycopg",
    "resume_after_sequence",
    "sse_streaming_response",
    "true_up_query_reservation",
    "wants_event_stream",
]
