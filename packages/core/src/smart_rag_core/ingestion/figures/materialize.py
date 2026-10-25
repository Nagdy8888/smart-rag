"""Render figures in the parser sandbox; describe bounded PNGs in the worker."""

from __future__ import annotations

import base64
import binascii
import hashlib
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import fitz
from smart_rag_core.ingestion.figures.limits import (
    FIGURE_DESCRIPTION_MAX_CHARS,
    FIGURE_MAX_PER_DOCUMENT,
    FIGURE_MAX_PIXELS,
    FIGURE_MAX_PNG_BYTES,
    FIGURE_MAX_SIDE_PIXELS,
    FIGURE_RENDER_DPI,
)
from smart_rag_core.ingestion.parser.types import ElementKind, ParseResult, TypedElement


@dataclass(frozen=True, slots=True)
class FigureAsset:
    """One PNG ready for private storage.

    Attributes:
        figure_id: Stable id copied onto the figure element.
        png: Bounded PNG bytes.
        content_hash: SHA-256 of ``png``.
        page_index: Zero-based page.
        caption: Nearby text, possibly empty.
        description: Vision text, possibly empty.
    """

    figure_id: str
    png: bytes
    content_hash: str
    page_index: int
    caption: str
    description: str


def materialize_pdf_figures(
    parse_result: ParseResult,
    pdf_bytes: bytes,
    describer: Callable[[bytes], str],
) -> tuple[ParseResult, tuple[FigureAsset, ...]]:
    """Crop each figure, describe it, and copy the text onto the element.

    Raster bytes come only from the isolated parser output. A failure or empty
    description keeps the image and any caption. Figures past the
    document cap are left unchanged.

    Args:
        parse_result: Closed parse that may contain figure elements.
        pdf_bytes: Original PDF bytes. Not logged.
        describer: One call per cropped PNG. Must not raise for provider
            failures it can turn into an empty string.

    Returns:
        Updated parse and the assets that were cropped.
    """

    if parse_result.format != "pdf" or not pdf_bytes:
        return parse_result, ()
    assets: list[FigureAsset] = []
    updated: list[TypedElement] = []
    kept = 0
    for element in parse_result.elements:
        png = _sandbox_png(element)
        clean_metadata = dict(element.metadata)
        clean_metadata.pop("sandbox_png", None)
        element = element.model_copy(update={"metadata": clean_metadata})
        if element.kind is not ElementKind.FIGURE or kept >= FIGURE_MAX_PER_DOCUMENT:
            updated.append(element)
            continue
        if not png or len(png) > FIGURE_MAX_PNG_BYTES:
            updated.append(element)
            continue
        kept += 1
        description = ""
        try:
            description = describer(png).strip()
        except (OSError, RuntimeError, ValueError):
            description = ""
        description = description[:FIGURE_DESCRIPTION_MAX_CHARS]
        caption = (element.text or "").strip()
        body = "\n".join(part for part in (caption, description) if part)
        figure_id = str(element.metadata.get("figure_id") or element.element_id)
        metadata = dict(element.metadata)
        metadata.pop("sandbox_png", None)
        metadata["content_hash"] = hashlib.sha256(png).hexdigest()
        if description:
            metadata["described"] = True
        updated.append(
            element.model_copy(
                update={
                    "text": body or None,
                    "media_only": not body,
                    "metadata": metadata,
                }
            )
        )
        assets.append(
            FigureAsset(
                figure_id=figure_id,
                png=png,
                content_hash=str(metadata["content_hash"]),
                page_index=_page_index(element),
                caption=caption,
                description=description,
            )
        )
    return parse_result.model_copy(update={"elements": tuple(updated)}), tuple(assets)


def _page_index(element: TypedElement) -> int:
    """Return the PDF page index stored on a figure locator."""

    page = getattr(element.locator, "page_index", 0)
    return page if isinstance(page, int) else 0


def _crop(document: fitz.Document, element: TypedElement) -> bytes:
    """Return PNG bytes for one figure, or empty when the crop fails."""

    doc = cast(Any, document)
    page_index = _page_index(element)
    page_count = doc.page_count
    if not isinstance(page_count, int) or page_index < 0 or page_index >= page_count:
        return b""
    page = doc.load_page(page_index)
    locator = element.locator
    box = (
        getattr(locator, "bbox_x0", None),
        getattr(locator, "bbox_y0", None),
        getattr(locator, "bbox_x1", None),
        getattr(locator, "bbox_y1", None),
    )
    coords: list[float] = []
    for value in box:
        if not isinstance(value, (int, float)):
            return b""
        coords.append(float(value))
    left, top, right, bottom = coords
    if not all(math.isfinite(value) for value in coords):
        return b""
    if right <= left or bottom <= top:
        return b""
    clip = fitz.Rect(left, top, right, bottom) & page.rect
    bounds = tuple(clip)
    if not all(math.isfinite(value) for value in bounds) or clip.is_empty:
        return b""
    # Include integer pixel rounding at both edges before native allocation.
    scale = FIGURE_RENDER_DPI / 72
    width = math.ceil(clip.x1 * scale) - math.floor(clip.x0 * scale)
    height = math.ceil(clip.y1 * scale) - math.floor(clip.y0 * scale)
    if (
        min(width, height) <= 0
        or max(width, height) > FIGURE_MAX_SIDE_PIXELS
        or width * height > FIGURE_MAX_PIXELS
    ):
        return b""
    pixmap = page.get_pixmap(clip=clip, dpi=FIGURE_RENDER_DPI, alpha=False)
    payload = pixmap.tobytes("png")
    return bytes(payload) if isinstance(payload, (bytes, bytearray)) else b""


def _sandbox_png(element: TypedElement) -> bytes:
    """Decode a size-bounded raster without opening a native image decoder."""
    encoded = element.metadata.get("sandbox_png")
    if not isinstance(encoded, str) or len(encoded) > 4 * (
        (FIGURE_MAX_PNG_BYTES + 2) // 3
    ):
        return b""
    try:
        png = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return b""
    if (
        len(png) < 24
        or len(png) > FIGURE_MAX_PNG_BYTES
        or not png.startswith(b"\x89PNG\r\n\x1a\n")
        or png[12:16] != b"IHDR"
    ):
        return b""
    width, height = struct.unpack(">II", png[16:24])
    if (
        min(width, height) == 0
        or max(width, height) > FIGURE_MAX_SIDE_PIXELS
        or width * height > FIGURE_MAX_PIXELS
    ):
        return b""
    return png


def render_pdf_figures(parse_result: ParseResult, pdf_bytes: bytes) -> ParseResult:
    """Run only inside the parser sandbox (or explicit synthetic test parser).

    Bounded rasters are transient parser output, stripped before canonical writes.
    Native PDF/image parsing never runs in the credential-bearing indexing worker.
    """
    if parse_result.format != "pdf" or not pdf_bytes:
        return parse_result
    updated: list[TypedElement] = []
    kept = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for element in parse_result.elements:
            if element.kind is ElementKind.FIGURE and kept < FIGURE_MAX_PER_DOCUMENT:
                kept += 1
                try:
                    png = _crop(document, element)
                except (RuntimeError, ValueError, OverflowError):
                    png = b""
                if png and len(png) <= FIGURE_MAX_PNG_BYTES:
                    element = element.model_copy(
                        update={
                            "metadata": {
                                **element.metadata,
                                "sandbox_png": base64.b64encode(png).decode("ascii"),
                            }
                        }
                    )
            updated.append(element)
    return parse_result.model_copy(update={"elements": tuple(updated)})
