"""One PDF page renders to PNG and out-of-range pages do not."""

from __future__ import annotations

from smart_rag_core.ingestion.parser.page_image import (
    CitationPageImageError,
    render_pdf_page_png,
)

from tests.support.pdf_fixture import empty_pdf


def _two_page_pdf() -> bytes:
    """Build a small in-memory PDF for page bounds and PNG tests."""
    document = empty_pdf()
    try:
        document.new_page()
        document.new_page()
        payload = document.tobytes()
    finally:
        document.close()
    return bytes(payload)


def test_render_pdf_page_png_returns_the_requested_page() -> None:
    """Page 2 of a two-page PDF becomes a PNG and nothing else."""

    png = render_pdf_page_png(_two_page_pdf(), 2)
    assert png.startswith(b"\x89PNG")


def test_render_pdf_page_png_rejects_a_missing_page() -> None:
    """A page past the end of the file raises and returns no image."""

    try:
        render_pdf_page_png(_two_page_pdf(), 9)
    except CitationPageImageError as exc:
        assert str(exc) == "page_missing"
    else:
        raise AssertionError("expected CitationPageImageError")


def _text_pdf(*, repeated: bool = False) -> bytes:
    """Build two native text lines with an optional ambiguous duplicate."""
    document = empty_pdf()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Checkpointing preserves the agent state")
        page.insert_text((72, 90), "between sessions without losing previous work.")
        if repeated:
            page.insert_text((72, 150), "Checkpointing preserves the agent state")
            page.insert_text(
                (72, 168), "between sessions without losing previous work."
            )
        return bytes(document.tobytes())
    finally:
        document.close()


def test_highlights_unique_multiline_evidence_without_changing_original() -> None:
    """One exact evidence sequence changes preview pixels, never stored bytes."""
    pdf = _text_pdf()
    plain = render_pdf_page_png(pdf, 1)
    highlighted = render_pdf_page_png(
        pdf,
        1,
        evidence_excerpt=(
            "Checkpointing preserves the agent state between sessions "
            "without losing previous work."
        ),
    )
    assert highlighted != plain
    assert render_pdf_page_png(pdf, 1) == plain


def test_ambiguous_or_inexact_evidence_stays_unhighlighted() -> None:
    """Repeated passages, short fragments and changed wording never guess."""
    excerpt = (
        "Checkpointing preserves the agent state between sessions "
        "without losing previous work."
    )
    duplicate = _text_pdf(repeated=True)
    assert render_pdf_page_png(duplicate, 1, evidence_excerpt=excerpt) == (
        render_pdf_page_png(duplicate, 1)
    )
    pdf = _text_pdf()
    plain = render_pdf_page_png(pdf, 1)
    for unmatched in (
        "agent state",
        excerpt.replace("preserves", "discards"),
        "x" * 8001,
    ):
        assert render_pdf_page_png(pdf, 1, evidence_excerpt=unmatched) == plain


def test_highlights_excerpt_cut_midword() -> None:
    """Citation excerpt character limits must not require whole boundary words."""
    pdf = _text_pdf()
    assert render_pdf_page_png(
        pdf,
        1,
        evidence_excerpt="pointing preserves the agent state between sessions without losing previous wo",
    ) != render_pdf_page_png(pdf, 1)


def test_highlights_pdf_line_hyphenation_and_ligatures() -> None:
    """Native line-end hyphens and typographic ligatures do not lose matches."""
    document = empty_pdf()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "Persistent check-")
        page.insert_text((72, 90), "pointing makes efficient recovery possible.")
        pdf = bytes(document.tobytes())
    finally:
        document.close()
    assert render_pdf_page_png(
        pdf,
        1,
        evidence_excerpt="Persistent checkpointing makes ef\ufb01cient recovery possible.",
    ) != render_pdf_page_png(pdf, 1)


def test_highlights_markdown_table_cells_in_column_major_pdf() -> None:
    """Table cells can be exact even when PDF text order differs from Markdown."""
    document = empty_pdf()
    try:
        page = document.new_page()
        for point, text in [
            ((72, 72), "Approach"),
            ((72, 100), "Object storage"),
            ((72, 140), "Vector stores"),
            ((250, 72), "Benefit"),
            ((250, 100), "Cheap durable storage"),
            ((250, 140), "Semantic search"),
            ((420, 72), "Limit"),
            ((420, 100), "Slow access"),
            ((420, 140), "Specialized setup"),
        ]:
            page.insert_text(point, text)
        pdf = bytes(document.tobytes())
    finally:
        document.close()
    excerpt = (
        "| Approach | Benefit | Limit |\n| --- | --- | --- |\n"
        "| Object storage | Cheap durable storage | Slow access |\n"
        "| Vector stores | Semantic search | Specialized setup |"
    )
    assert render_pdf_page_png(pdf, 1, evidence_excerpt=excerpt) != render_pdf_page_png(
        pdf, 1
    )


def test_a_lone_common_table_cell_is_not_enough() -> None:
    """A stray matching table cell cannot select unrelated page text."""
    assert render_pdf_page_png(
        _text_pdf(),
        1,
        evidence_excerpt="| Unknown policy | agent state | Missing evidence |",
    ) == render_pdf_page_png(_text_pdf(), 1)
