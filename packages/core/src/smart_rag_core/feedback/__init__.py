"""Feedback tag catalog."""

from smart_rag_core.feedback.tags import (
    FEEDBACK_TAGS,
    FEEDBACK_TAGS_DOWN,
    FEEDBACK_TAGS_UP,
    FeedbackTag,
    FeedbackTagError,
    feedback_tags_for,
    require_feedback_tag,
)

__all__ = [
    "FEEDBACK_TAGS",
    "FEEDBACK_TAGS_DOWN",
    "FEEDBACK_TAGS_UP",
    "FeedbackTag",
    "FeedbackTagError",
    "feedback_tags_for",
    "require_feedback_tag",
]
