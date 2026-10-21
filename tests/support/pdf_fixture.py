"""Typed boundary for PyMuPDF's dynamically installed test-fixture methods."""

from __future__ import annotations

from typing import Protocol, cast

import fitz


class PdfPage(Protocol):
    """Drawing operations exercised by native PDF fixtures."""

    def insert_text(
        self,
        point: tuple[int, int],
        text: str,
        *,
        fontsize: int = 11,
        fontname: str = "helv",
    ) -> int:
        """Write fixture text at a physical position."""
        ...

    def insert_image(self, rect: fitz.Rect, *, pixmap: object) -> int:
        """Place a fixture raster."""
        ...


class PdfDocument(Protocol):
    """PDF fixture writer used by rendering and ingestion tests."""

    def new_page(self) -> PdfPage:
        """Append an empty page."""
        ...

    def tobytes(self) -> bytes:
        """Serialize the fixture."""
        ...

    def close(self) -> None:
        """Release the fixture handle."""
        ...


class PdfPixmap(Protocol):
    """Only the fixture pixel-fill operation lacks a complete vendor signature."""

    def clear_with(self, value: int) -> None:
        """Fill the fixture raster with one value."""
        ...


def empty_pdf() -> PdfDocument:
    """Open a real PyMuPDF writer with its narrow tested method contract."""
    return cast(PdfDocument, fitz.open())


def fill_pixmap(pixmap: object, value: int) -> None:
    """Fill a real fixture pixmap through the typed dynamic-method boundary."""
    cast(PdfPixmap, pixmap).clear_with(value)
