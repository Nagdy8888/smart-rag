"""Shared SSE service constants."""

from __future__ import annotations

CANCEL_GRACE_SECONDS = 0.25
"""Cooperative executor cleanup window after an explicit cancel."""

POLL_SECONDS = 0.05
"""Attach-loop poll interval in seconds when no live handle can wake it."""

ATTACH_IDLE_POLL_SECONDS = 0.5
"""Longest attach-loop wait for a run this process is executing.

Every append made by this process wakes the attach loop at once, so this
only bounds a missed wake-up."""

NON_STARTABLE_STATUSES = frozenset(
    {"running", "completed", "cancelled", "partial", "failed"}
)
