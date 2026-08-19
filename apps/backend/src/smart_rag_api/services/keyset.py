"""Keyset cursor parsing for bounded list endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from smart_rag_core.query_admission.exceptions import QueryAdmissionError


def parse_created_at_id_cursor(
    cursor: str | None,
) -> tuple[datetime | None, UUID | None]:
    """Parse a ``created_at,id`` keyset cursor.

    Args:
        cursor: Optional opaque cursor from the client. Empty is the first page.

    Returns:
        ``(created_at, id)`` or ``(None, None)`` for the first page.

    Raises:
        QueryAdmissionError: ``invalid_cursor`` when the value is malformed.
    """

    if cursor is None or not cursor.strip():
        return None, None
    raw = cursor.strip()
    if "," not in raw:
        raise QueryAdmissionError("invalid_cursor")
    stamp_text, _, id_text = raw.partition(",")
    try:
        created_at = datetime.fromisoformat(stamp_text)
        item_id = UUID(id_text)
    except (TypeError, ValueError) as exc:
        raise QueryAdmissionError("invalid_cursor") from exc
    return created_at, item_id


def format_created_at_id_cursor(created_at: datetime, item_id: UUID) -> str:
    """Serialize one keyset cursor.

    Args:
        created_at: Row creation timestamp.
        item_id: Row primary key.

    Returns:
        ``created_at,id`` token.
    """

    return f"{created_at.isoformat()},{item_id}"
