"""Shared SSE service constants."""

from __future__ import annotations

CANCEL_GRACE_SECONDS = 0.25
"""Cooperative executor cleanup window after an explicit cancel."""

POLL_SECONDS = 0.05
"""Attach-loop poll interval in seconds while waiting for persisted events."""

NON_STARTABLE_STATUSES = frozenset(
    {"running", "completed", "cancelled", "partial", "failed"}
)
