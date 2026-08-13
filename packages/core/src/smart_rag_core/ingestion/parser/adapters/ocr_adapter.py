# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false
"""OCR adapter for scanned PDF pages using Tesseract."""

from __future__ import annotations

import hashlib
import io
from typing import TYPE_CHECKING, Any, cast

import pytesseract
from PIL import Image

from smart_rag_core.ingestion.parser.helpers import element_id
from smart_rag_core.ingestion.parser.limits import (
    OCR_CONFIG_VERSION,
    OCR_DPI,
    OCR_LANGUAGES,
    OCR_MIN_CONFIDENCE,
    OCR_OEM,
    OCR_PSM,
)
from smart_rag_core.ingestion.parser.types import ElementKind, OcrLocator, TypedElement

if TYPE_CHECKING:
    import fitz


def parse_scanned_pdf_page(
    page: fitz.Page,
    page_index: int,
    content_hash: str,
) -> tuple[TypedElement, ...]:
    """OCR one scanned PDF page and emit boxed text elements.

    Args:
        page: PyMuPDF page object.
        page_index: Zero-based page index.
        content_hash: Source object hash for stable IDs.

    Returns:
        Typed OCR elements with confidence and page hash; empty when OCR unavailable.
    """

    page_any = cast(Any, page)
    pixmap = page_any.get_pixmap(dpi=OCR_DPI)
    rendered_hash = hashlib.sha256(bytes(pixmap.tobytes())).hexdigest()
    image = Image.open(io.BytesIO(bytes(pixmap.tobytes("png"))))
    try:
        data = cast(
            dict[str, list[object]],
            pytesseract.image_to_data(
                image,
                lang=OCR_LANGUAGES,
                config=f"--oem {OCR_OEM} --psm {OCR_PSM}",
                output_type=pytesseract.Output.DICT,
            ),
        )
    except pytesseract.TesseractNotFoundError:
        return (
            TypedElement(
                element_id=element_id(
                    content_hash,
                    page_index,
                    ElementKind.FIGURE,
                    OcrLocator(
                        page_index=page_index,
                        bbox_x0=0.0,
                        bbox_y0=0.0,
                        bbox_x1=float(pixmap.width),
                        bbox_y1=float(pixmap.height),
                        confidence=0.0,
                        rendered_page_hash=rendered_hash,
                    ),
                    None,
                ),
                kind=ElementKind.FIGURE,
                text=None,
                reading_order=page_index * 1000,
                locator=OcrLocator(
                    page_index=page_index,
                    bbox_x0=0.0,
                    bbox_y0=0.0,
                    bbox_x1=float(pixmap.width),
                    bbox_y1=float(pixmap.height),
                    confidence=0.0,
                    rendered_page_hash=rendered_hash,
                    engine_version=OCR_CONFIG_VERSION,
                ),
                media_only=True,
                metadata={"ocr_unavailable": True},
            ),
        )

    elements: list[TypedElement] = []
    order_base = page_index * 1000
    for index in range(len(data["text"])):
        text = str(data["text"][index]).strip()
        conf = float(data["conf"][index])
        if not text or conf < OCR_MIN_CONFIDENCE:
            continue
        x = float(data["left"][index])
        y = float(data["top"][index])
        w = float(data["width"][index])
        h = float(data["height"][index])
        locator = OcrLocator(
            page_index=page_index,
            bbox_x0=x,
            bbox_y0=y,
            bbox_x1=x + w,
            bbox_y1=y + h,
            confidence=conf,
            rendered_page_hash=rendered_hash,
            engine_version=OCR_CONFIG_VERSION,
        )
        reading_order = order_base + index
        elements.append(
            TypedElement(
                element_id=element_id(
                    content_hash, reading_order, ElementKind.PARAGRAPH, locator, text
                ),
                kind=ElementKind.PARAGRAPH,
                text=text,
                reading_order=reading_order,
                locator=locator,
            )
        )
    if not elements:
        return (
            TypedElement(
                element_id=element_id(
                    content_hash,
                    order_base,
                    ElementKind.FIGURE,
                    OcrLocator(
                        page_index=page_index,
                        bbox_x0=0.0,
                        bbox_y0=0.0,
                        bbox_x1=float(pixmap.width),
                        bbox_y1=float(pixmap.height),
                        confidence=0.0,
                        rendered_page_hash=rendered_hash,
                    ),
                    None,
                ),
                kind=ElementKind.FIGURE,
                text=None,
                reading_order=order_base,
                locator=OcrLocator(
                    page_index=page_index,
                    bbox_x0=0.0,
                    bbox_y0=0.0,
                    bbox_x1=float(pixmap.width),
                    bbox_y1=float(pixmap.height),
                    confidence=0.0,
                    rendered_page_hash=rendered_hash,
                    engine_version=OCR_CONFIG_VERSION,
                ),
                media_only=True,
            ),
        )
    return tuple(elements)
