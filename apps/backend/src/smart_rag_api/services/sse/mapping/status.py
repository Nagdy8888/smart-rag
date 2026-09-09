"""Status-event mapping for compiled graph node updates."""

from __future__ import annotations

from smart_rag_api.services.sse.mapping.contracts import (
    DEADLINE_EXHAUSTED_DETAIL,
    REJECT_STATUSES,
)


def status_event(
    node_name: str, update: dict[str, object]
) -> tuple[str, dict[str, object]]:
    """Build one allow-listed status event for a node update.

    Args:
        node_name: Compiled graph node name.
        update: Node return mapping.

    Returns:
        ``status`` event with stage, status, and completion phase.
    """

    raw_status = update.get("status")
    status = (
        raw_status[:64] if isinstance(raw_status, str) and raw_status else "running"
    )
    phase = "failed" if status in REJECT_STATUSES else "completed"
    return (
        "status",
        {"stage": node_name[:64], "status": status, "phase": phase},
    )


def reject_terminal_events(
    update: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    """Map a fail-closed node status to the catalog terminal sequence.

    Retrieve-time ``deadline_exhausted`` uses ``deadline`` then ``partial``,
    matching the executor pre-check. Other rejects stay ``error`` with the
    node status as ``code``. ``detail`` is never copied onto ``error``.

    Args:
        update: Node return mapping with ``status`` and optional ``detail``.

    Returns:
        Empty when ``status`` is not a reject status. Otherwise one
        terminal sequence.
    """

    raw_status = update.get("status")
    if not isinstance(raw_status, str) or raw_status not in REJECT_STATUSES:
        return []
    detail = update.get("detail")
    if detail == DEADLINE_EXHAUSTED_DETAIL:
        return [
            ("deadline", {}),
            ("partial", {"reason": DEADLINE_EXHAUSTED_DETAIL}),
        ]
    return [("error", {"code": raw_status})]
