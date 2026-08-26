"""HTTP Accept/resume helpers and the default executor factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from smart_rag_api.services.sse.executors import (
    LangGraphQueryRunExecutor,
    QueryRunExecutor,
)

SSE_RESPONSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def wants_event_stream(accept: str | None) -> bool:
    """Return whether ``Accept`` asks for SSE.

    Args:
        accept: Accept header.

    Returns:
        True when ``text/event-stream`` is present.
    """

    if accept is None:
        return False
    return "text/event-stream" in accept.lower()


def resume_after_sequence(after: int, last_event_id: str | None) -> int:
    """Combine ``after`` with SSE ``Last-Event-ID``.

    Args:
        after: Query parameter. ``0`` means from the start unless Last-Event-ID
            is higher.
        last_event_id: Optional SSE reconnect header.

    Returns:
        Exclusive cursor. Invalid Last-Event-ID values are ignored.
    """

    header_value = 0
    if last_event_id is not None and last_event_id.strip().isdigit():
        header_value = int(last_event_id.strip())
    return max(after, header_value)


def sse_streaming_response(frames: AsyncIterator[str]) -> StreamingResponse:
    """Build a ``text/event-stream`` response with no-buffering headers.

    Args:
        frames: Persist-then-flush iterator.

    Returns:
        StreamingResponse whose headers win over middleware ``setdefault``.
    """

    return StreamingResponse(
        frames,
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


def default_executor_factory() -> QueryRunExecutor:
    """Return the production LangGraph executor.

    Returns:
        LangGraph-backed executor. Import-safe until ``execute`` runs.
    """

    return LangGraphQueryRunExecutor()
