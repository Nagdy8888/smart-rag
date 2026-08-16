"""Phase 7 packet 5: accessibility and security specification review."""

from __future__ import annotations

from pathlib import Path

REVIEW = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "frontend"
    / "STITCH_A11Y_SECURITY.md"
)


def test_a11y_review_covers_keyboard_rtl_and_live_regions() -> None:
    """Keyboard, mixed-direction, mobile, and live-region rules are recorded."""

    text = REVIEW.read_text(encoding="utf-8")
    for token in (
        "Skip link",
        "Focus visible",
        "Live assertive",
        "Reduced motion",
        "390px",
        "200% zoom",
            "Logical offsets",
        "dir=\"auto\"",
        "WCAG AA",
        "dangerouslySetInnerHTML",
        "isSafeHttpUrl",
        "GAP-07-09",
        "APP_ENV=test",
        "not an accessibility waiver",
    ):
        assert token in text, token


def test_a11y_review_includes_xss_and_forged_role() -> None:
    """Negative fixtures and server-enforced authz are explicit."""

    text = REVIEW.read_text(encoding="utf-8")
    assert "<img src=x onerror=alert(1)>.pdf" in text
    assert "Forged admin POST" in text
    assert "UI hide convenience only" in text
