"""Feedback tag polarity catalog."""

from smart_rag_core.feedback.tags import (
    FEEDBACK_TAGS,
    FEEDBACK_TAGS_DOWN,
    FEEDBACK_TAGS_UP,
    FeedbackTagError,
    feedback_tags_for,
    require_feedback_tag,
)


def test_polarity_catalogs_stay_disjoint_and_unmerged() -> None:
    """Up and down tags do not overlap; the ten diagnostics remain."""

    assert FEEDBACK_TAGS_UP.isdisjoint(FEEDBACK_TAGS_DOWN)
    assert FEEDBACK_TAGS == FEEDBACK_TAGS_UP | FEEDBACK_TAGS_DOWN
    assert "chunk/cleaning loss" in FEEDBACK_TAGS_DOWN
    assert "helpful answer" in FEEDBACK_TAGS_UP
    assert feedback_tags_for(True) == FEEDBACK_TAGS_UP
    assert feedback_tags_for(False) == FEEDBACK_TAGS_DOWN


def test_require_feedback_tag_accepts_both_polarities() -> None:
    """Both polarity catalogs persist; unknown strings fail."""

    assert require_feedback_tag("helpful answer") == "helpful answer"
    assert require_feedback_tag("wrong route") == "wrong route"
    try:
        require_feedback_tag("merged-tag")
    except FeedbackTagError as exc:
        assert str(exc) == "invalid_tag"
    else:
        raise AssertionError("merged-tag must be rejected")
