"""Phase 7 packet 2: Stitch brief localization, tokens, and prompt honesty."""

from __future__ import annotations

from pathlib import Path

BRIEF_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "frontend" / "STITCH_BRIEF.md"
)


def test_brief_records_english_chrome_and_arabic_content() -> None:
    """v1 localizes chrome to English and isolates Arabic content."""

    brief = BRIEF_PATH.read_text(encoding="utf-8")
    assert "**v1 chrome is English.**" in brief
    assert 'dir="auto"' in brief
    assert "unicode-bidi: isolate" in brief
    assert "logical Unicode offsets" in brief
    assert "GAP-07-19" in brief


def test_brief_reconciles_tokens_and_rejects_blur() -> None:
    """One token set exists; blur and Tailwind CDN are rejected."""

    brief = BRIEF_PATH.read_text(encoding="utf-8")
    assert "--color-accent" in brief
    assert "#4E5BD5" in brief
    assert "**Blur is rejected**" in brief
    assert "runtime Tailwind CDN" in brief
    assert "--radius-md" in brief


def test_brief_has_copy_ready_prompts_for_canonical_surfaces() -> None:
    """Every canonical screen family has a copy-ready prompt block."""

    brief = BRIEF_PATH.read_text(encoding="utf-8")
    for heading in (
        "### A. Sign in",
        "### B. Sign up",
        "### C. Forgot / reset password / callback",
        "### D. MFA enrollment / challenge / required",
        "### E. Invitation accept / owner setup / team",
        "### F. Main chat (Auto)",
        "### H. Document library / upload / crawl / status",
        "### I. Document detail",
        "### J. Graph explorer",
        "### K. Structured tables",
        "### L. Tools, glossary, entity rules",
        "### M. Usage, audit, profile, company settings",
    ):
        assert heading in brief, heading
    assert "Auto is the default chat route" in brief
    assert "Do not invent API fields" in brief


def test_brief_negative_review_forbids_mock_diagnostics() -> None:
    """Prompts must not treat graph-only or BM25 snippets as answers."""

    brief = BRIEF_PATH.read_text(encoding="utf-8")
    assert "Do not show graph-only as a normal answering mode" in brief
    assert "BM25 snippet as a citation" in brief
    assert "<img src=x onerror=alert(1)>.pdf" in brief
    assert "Desktop 1280" in brief
    assert "390" in brief
