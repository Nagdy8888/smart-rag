"""Allow-listed Phase 6 feedback tags. Tags are never merged."""

from __future__ import annotations

from typing import Literal

FeedbackTag = Literal[
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
]

FEEDBACK_TAGS: frozenset[str] = frozenset(
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
    }
)


class FeedbackTagError(ValueError):
    """Raised when feedback is missing a tag or uses an unknown string."""


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
