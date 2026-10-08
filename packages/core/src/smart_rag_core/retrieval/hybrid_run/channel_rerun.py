"""One extra channel pass when the first pass was empty only because of time."""

from __future__ import annotations

from smart_rag_core.retrieval.profiles import CHANNEL_RERUN_MIN_REMAINING_SECONDS


def should_rerun_channels(
    fused_empty: bool,
    timed_out: bool,
    remaining_run_seconds: float,
) -> bool:
    """Return whether the channel phase may run once more.

    Args:
        fused_empty: True when dense, BM25, and term contributed no IDs.
        timed_out: True when at least one channel missed its deadline.
        remaining_run_seconds: Seconds left on the admitted run, not the
            retrieval slice.

    Returns:
        True only when fusion is empty, a channel timed out, and at least
        ``CHANNEL_RERUN_MIN_REMAINING_SECONDS`` remain.
    """

    return (
        fused_empty
        and timed_out
        and remaining_run_seconds >= CHANNEL_RERUN_MIN_REMAINING_SECONDS
    )
