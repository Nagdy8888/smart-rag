"""Status-event mapping for compiled graph node updates."""

from __future__ import annotations

from smart_rag_api.services.sse.mapping.contracts import REJECT_STATUSES


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
