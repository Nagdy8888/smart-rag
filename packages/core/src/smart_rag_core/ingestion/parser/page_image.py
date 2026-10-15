"""Render one PDF page to a bounded PNG.

The caller already checked access. This module never returns the PDF bytes
and never builds a Storage URL.
"""

from __future__ import annotations

import math

import fitz

MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PAGE_PIXELS = 4_000_000
MAX_PNG_BYTES = 8 * 1024 * 1024
_BASE_ZOOM = 120 / 72


class CitationPageImageError(ValueError):
    """The requested page cannot be rendered inside the size cap."""


def render_pdf_page_png(pdf_bytes: bytes, page_number: int) -> bytes:
    """Render one 1-based PDF page to PNG at 120 DPI, scaled down if needed.

    Args:
        pdf_bytes: Original PDF bytes already loaded by an authorized caller.
        page_number: 1-based file page. This is the page Acrobat opens.

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
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_number > document.page_count:
            raise CitationPageImageError("page_missing")
        page = document[page_number - 1]
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
