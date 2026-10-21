"""One PDF page renders to PNG and out-of-range pages do not."""

from __future__ import annotations

from smart_rag_core.ingestion.parser.page_image import (
    CitationPageImageError,
    render_pdf_page_png,
)

from tests.support.pdf_fixture import empty_pdf


def _two_page_pdf() -> bytes:
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
