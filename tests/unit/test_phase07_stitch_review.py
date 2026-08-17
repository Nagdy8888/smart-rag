"""Phase 7 packet 6: fallback selection is explicit and bounded."""

from __future__ import annotations

from pathlib import Path

REVIEW = (
    Path(__file__).resolve().parents[2] / "docs" / "frontend" / "STITCH_REVIEW.md"
)


def test_review_selects_component_fallback_within_timebox() -> None:
    """Fallback is dated, bounded to two rounds, and names Phase 8 primitives."""

    text = REVIEW.read_text(encoding="utf-8")
    assert "Opened | 2026-08-17" in text or "Opened | 2026-08-17" in text.replace(
        "| ", "| "
    )
    assert "2 of 2" in text
    assert "0 of 2" not in text
    assert "1 of 2" not in text
    assert "component-system fallback" in text
    assert "native HTML" in text
    assert "**No** runtime Tailwind CDN" in text
    assert "template, not a layout" in text
    assert "do not add it" in text
    assert "Stitch frames added as routes | **none**" in text
    assert "Stitch HTML accepted as production | **no**" in text
    assert "Do not copy Stitch" in text
    assert "GAP-07-07" in text
    assert "five business days" in text


def test_review_rejects_indefinite_wait_and_bundle_approval() -> None:
    """Negative: bundle presence and open-ended Stitch waiting are rejected."""

    text = REVIEW.read_text(encoding="utf-8")
    assert "Bundle presence" in text
    assert "third revision round is forbidden" in text
    assert "Indefinite wait" in text
