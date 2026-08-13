"""Bounded exponential backoff with jitter for transient job failures."""

from __future__ import annotations

import random

from smart_rag_core.jobs.limits import (
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_BACKOFF_MAX_SECONDS,
    RETRY_JITTER_FRACTION,
)


def compute_retry_delay_seconds(
    attempt_count: int,
    *,
    base_seconds: int = RETRY_BACKOFF_BASE_SECONDS,
    max_seconds: int = RETRY_BACKOFF_MAX_SECONDS,
    jitter_fraction: float = RETRY_JITTER_FRACTION,
) -> int:
    """Compute the next retry delay from the attempt count.

    Args:
        attempt_count: One-based attempt count after a failed run.
        base_seconds: Exponential base delay.
        max_seconds: Hard ceiling for retry delay.
        jitter_fraction: Randomized fraction added/subtracted from the delay.

    Returns:
        Non-negative delay in seconds before the job may be reclaimed.

    Side Effects:
        Uses ``random.random`` for jitter.
    """

    bounded_attempt = max(attempt_count, 1)
    exponent = min(bounded_attempt - 1, 10)
    delay = min(base_seconds * (2**exponent), max_seconds)
    jitter_span = int(delay * jitter_fraction)
    if jitter_span <= 0:
        return delay
    return max(0, delay + random.randint(-jitter_span, jitter_span))  # noqa: S311
