"""SSE package: chunk parse, executors, registry, service, and HTTP framing."""

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

__all__ = [
    "CANCEL_GRACE_SECONDS",
    "SSE_RESPONSE_HEADERS",
    "FixtureQueryRunExecutor",
    "LangGraphQueryRunExecutor",
    "LiveQueryRun",
    "QueryRunExecutor",
    "QueryRunRegistry",
    "SseStreamService",
    "coerce_stream_token_count",
    "default_executor_factory",
    "resume_after_sequence",
    "sse_streaming_response",
    "token_counts_from_update",
    "updates_mapping_from_chunk",
    "wants_event_stream",
]
