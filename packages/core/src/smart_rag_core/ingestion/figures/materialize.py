"""Crop PDF figures and attach a description without the parser sandbox."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import fitz
from smart_rag_core.ingestion.figures.limits import (
    FIGURE_DESCRIPTION_MAX_CHARS,
    FIGURE_MAX_PER_DOCUMENT,
    FIGURE_MAX_PNG_BYTES,
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

    The describer runs outside the parser sandbox. A failure or empty
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
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except RuntimeError:
        return parse_result, ()
    assets: list[FigureAsset] = []
    updated: list[TypedElement] = []
    kept = 0
    try:
        for element in parse_result.elements:
            if element.kind is not ElementKind.FIGURE or kept >= FIGURE_MAX_PER_DOCUMENT:
                updated.append(element)
                continue
            png = _crop(document, element)
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
    finally:
        document.close()
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
    xref = element.metadata.get("xref")
    if isinstance(xref, int) and xref > 0:
        try:
            extracted = doc.extract_image(xref)
        except (RuntimeError, ValueError):
            extracted = None
        info = (
            cast(dict[str, object], extracted) if isinstance(extracted, dict) else None
        )
        if info is not None:
            raw = info.get("image")
            if info.get("ext") == "png" and isinstance(raw, (bytes, bytearray)):
                return bytes(raw)
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
    if right <= left or bottom <= top:
        return b""
    clip = fitz.Rect(left, top, right, bottom)
    pixmap = page.get_pixmap(clip=clip, dpi=120)
    payload = pixmap.tobytes("png")
    return bytes(payload) if isinstance(payload, (bytes, bytearray)) else b""
