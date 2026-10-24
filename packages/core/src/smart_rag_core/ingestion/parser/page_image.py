"""Render one PDF page to a bounded PNG.

The caller already checked access. This module never returns the PDF bytes
and never builds a Storage URL.
"""

from __future__ import annotations

import math
from typing import Protocol, cast

import fitz

from .page_highlights import HighlightPage, highlight_cited_passage

MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PAGE_PIXELS = 4_000_000
MAX_PNG_BYTES = 8 * 1024 * 1024
_BASE_ZOOM = 120 / 72


class CitationPageImageError(ValueError):
    """The requested page cannot be rendered inside the size cap."""


class _Pixmap(Protocol):
    """Typed boundary for dynamically installed PyMuPDF image methods."""

    def tobytes(self, output: str) -> object:
        """Encode the rendered page."""
        ...


class _Rect(Protocol):
    """Physical page dimensions supplied by the PDF renderer."""

    width: float
    height: float


class _Page(Protocol):
    """Page operations needed for bounded preview rendering."""

    rect: _Rect

    def get_pixmap(self, *, matrix: fitz.Matrix, alpha: bool) -> _Pixmap:
        """Render at the caller's bounded scale."""
        ...


class _Document(Protocol):
    """Minimal PDF reader contract independent of incomplete vendor stubs."""

    page_count: int

    def __getitem__(self, index: int) -> _Page:
        """Read one page by physical index."""
        ...

    def close(self) -> None:
        """Release the PDF handle."""
        ...


def render_pdf_page_png(
    pdf_bytes: bytes, page_number: int, *, evidence_excerpt: str | None = None
) -> bytes:
    """Render one 1-based PDF page to PNG at 120 DPI, scaled down if needed.

    Args:
        pdf_bytes: Original PDF bytes already loaded by an authorized caller.
        page_number: 1-based file page. This is the page Acrobat opens.
        evidence_excerpt: Optional authorized stored passage for exact highlighting.

    Returns:
        PNG bytes for that page only.

    Raises:
        CitationPageImageError: When the file, page, or image is outside
            the cap, or the bytes are not a PDF page.
    """

    if page_number < 1 or page_number > 5000:
        raise CitationPageImageError("page_missing")
    if len(pdf_bytes) == 0 or len(pdf_bytes) > MAX_PDF_BYTES:
        raise CitationPageImageError("pdf_rejected")
    document = cast(_Document, fitz.open(stream=pdf_bytes, filetype="pdf"))
    try:
        if page_number > document.page_count:
            raise CitationPageImageError("page_missing")
        page = document[page_number - 1]
        if evidence_excerpt:
            highlight_cited_passage(cast(HighlightPage, page), evidence_excerpt)
        rect = page.rect
        zoom = _BASE_ZOOM
        pixels = rect.width * zoom * rect.height * zoom
        if pixels > MAX_PAGE_PIXELS and pixels > 0:
            zoom *= math.sqrt(MAX_PAGE_PIXELS / pixels)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        payload = pixmap.tobytes("png")
    finally:
        document.close()
    if not isinstance(payload, (bytes, bytearray)) or not bytes(payload).startswith(
        b"\x89PNG"
    ):
        raise CitationPageImageError("render_failed")
    png = bytes(payload)
    if len(png) > MAX_PNG_BYTES:
        raise CitationPageImageError("png_rejected")
    return png
