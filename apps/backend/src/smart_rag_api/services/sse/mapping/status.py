"""Status-event mapping for compiled graph node updates."""

from __future__ import annotations


def status_event(
    node_name: str, update: dict[str, object]
) -> tuple[str, dict[str, object]]:
    """Build one allow-listed status event for a node update.

    Args:
        node_name: Compiled graph node name.
        update: Node return mapping.

    Returns:
        ``status`` event with stage and status only.
    """

    raw_status = update.get("status")
    status = (
        raw_status[:64] if isinstance(raw_status, str) and raw_status else "running"
    )
    return ("status", {"stage": node_name[:64], "status": status})
