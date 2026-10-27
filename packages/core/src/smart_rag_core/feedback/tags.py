"""Allow-listed feedback tags. Diagnostic and positive tags stay unmerged."""

from __future__ import annotations

from typing import Literal

FeedbackTag = Literal[
    "helpful answer",
    "accurate citation",
    "correct route",
    "correct calculation",
    "sufficient graph",
    "chunk/cleaning loss",
    "profile field wrong",
    "candidate miss",
    "wrong rerank",
    "bad refusal/overconfident answer",
    "missed relationship",
    "wrong route",
    "wrong calculation",
    "bad citation",
    "insufficient graph",
    "incorrect answer",
    "outdated answer",
    "incomplete answer",
    "wrong source",
]

FEEDBACK_TAGS_UP: frozenset[str] = frozenset(
    {
        "helpful answer",
        "accurate citation",
        "correct route",
        "correct calculation",
        "sufficient graph",
    }
)

FEEDBACK_TAGS_DOWN: frozenset[str] = frozenset(
    {
        "chunk/cleaning loss",
        "profile field wrong",
        "candidate miss",
        "wrong rerank",
        "bad refusal/overconfident answer",
        "missed relationship",
        "wrong route",
        "wrong calculation",
        "bad citation",
        "insufficient graph",
        "incorrect answer",
        "outdated answer",
        "incomplete answer",
        "wrong source",
    }
)

FEEDBACK_TAGS: frozenset[str] = FEEDBACK_TAGS_UP | FEEDBACK_TAGS_DOWN


class FeedbackTagError(ValueError):
    """Raised when feedback is missing a tag or uses an unknown string."""


def feedback_tags_for(thumbs_up: bool) -> frozenset[str]:
    """Return the polarity-specific catalog.

    Args:
        thumbs_up: True for thumbs-up tags.

    Returns:
        Exact unmerged tags for that polarity.
    """

    return FEEDBACK_TAGS_UP if thumbs_up else FEEDBACK_TAGS_DOWN


def require_feedback_tag(tag: str | None) -> str:
    """Return the tag when it is exactly one allow-listed value.

    Args:
        tag: Client-supplied tag. Must match a catalog string byte-for-byte.

    Returns:
        The validated tag.

    Raises:
        FeedbackTagError: When the tag is missing or not in the catalog.
    """

    if tag is None or tag not in FEEDBACK_TAGS:
        raise FeedbackTagError("invalid_tag")
    return tag
