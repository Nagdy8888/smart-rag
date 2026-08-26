"""Structured metadata logs for dropped custom progress payloads."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def log_dropped_custom(
    *,
    reason: str,
    kind: str | None,
    extra_keys: tuple[str, ...],
) -> None:
    """Log why a custom payload was dropped. Never log payload values.

    Args:
        reason: Stable drop reason.
        kind: Claimed ``kind`` when it was a string.
        extra_keys: Unexpected key names only.
    """

    LOGGER.info(
        "sse_custom_progress_dropped",
        extra={
            "reason": reason[:64],
            "kind": (kind or "")[:64],
            "extra_keys": extra_keys[:16],
        },
    )
