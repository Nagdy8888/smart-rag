"""Input safety for untrusted user and memory text."""

from __future__ import annotations

from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import MemoryRecord

_MAX_QUERY_CHARS = 2000


def sanitize_user_text(text: str) -> str:
    """Treat user text as untrusted, bound it, and strip NULs.

    Args:
        text: Raw user query.

    Returns:
        Bounded query text. Meaning is not rewritten.

    Raises:
        QueryRoutingError: Empty or over-long input.
    """

    cleaned = text.replace("\x00", "")
    stripped = cleaned.strip()
    if not stripped:
        raise QueryRoutingError("empty_query")
    if len(cleaned) > _MAX_QUERY_CHARS:
        raise QueryRoutingError("query_exceeds_bounds")
    return cleaned


def delimit_memory_record(
    *,
    message_id: str,
    role: str,
    content: str,
    created_at: str,
) -> MemoryRecord:
    """Wrap one message as an untrusted delimited record.

    Args:
        message_id: Message UUID string.
        role: Message role.
        content: Truncated body. Never a source document.
        created_at: Timestamp string.

    Returns:
        Frozen memory record with instruction-safe delimiters.
    """

    safe_role = role.replace(">>", "")
    body = content.replace("<<", "").replace(">>", "")
    delimited = (
        f"<<untrusted-memory id={message_id} role={safe_role} created={created_at}>>\n"
        f"{body}\n"
        "<</untrusted-memory>>"
    )
    return MemoryRecord(
        message_id=message_id,
        role=safe_role,
        content=body[:1500],
        created_at=created_at,
        delimited=delimited[:2048],
    )
