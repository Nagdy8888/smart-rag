# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportAttributeAccessIssue=false
"""PDF adapter using PyMuPDF with OCR handoff for scanned pages."""

from __future__ import annotations

import time
from pathlib import Path

import fitz

from smart_rag_core.ingestion.parser.adapters.ocr_adapter import parse_scanned_pdf_page
from smart_rag_core.ingestion.parser.cleaning.pdf_headers import (
    detect_repeated_lines,
    remove_repeated_lines,
)
from smart_rag_core.ingestion.parser.exceptions import (
    ParserEncryptedError,
    ParserLimitExceeded,
)
from smart_rag_core.ingestion.parser.helpers import build_coverage, element_id
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PARSER_CONFIG_VERSION,
    PDF_MAX_PAGES,
)
from smart_rag_core.ingestion.parser.types import (
    ElementKind,
    OcrLocator,
    ParseDisposition,
    ParseResult,
    ParserResourceMetrics,
    PdfLocator,
    SourceLocator,
    TypedElement,
)


def parse_pdf(path: Path, content_hash: str, format_key: str) -> ParseResult:
    """Parse a PDF into typed elements with page locators and OCR fallback."""

    started = time.monotonic()
    try:
        document = fitz.open(path)
    except RuntimeError as exc:
        if "password" in str(exc).lower():
            raise ParserEncryptedError("password-protected PDF") from exc
        raise
    if document.needs_pass:
        raise ParserEncryptedError("password-protected PDF")
    if document.page_count > PDF_MAX_PAGES:
        raise ParserLimitExceeded("pages", f"page count {document.page_count}")

    page_lines: list[list[str]] = []
    sortable: list[tuple[int, TypedElement]] = []
    ocr_pages = 0
    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        text = page.get_text("text")
        page_lines.append(text.splitlines())
        sortable.append(
            (
                page_index * 10_000,
                TypedElement(
                    element_id=element_id(
                        content_hash,
                        page_index,
                        ElementKind.PAGE_BREAK,
                        PdfLocator(page_index=page_index),
                        None,
                    ),
                    kind=ElementKind.PAGE_BREAK,
                    text=None,
                    reading_order=page_index,
                    locator=PdfLocator(page_index=page_index),
                ),
            )
        )
        if not text.strip():
            ocr_elements = parse_scanned_pdf_page(page, page_index, content_hash)
            if ocr_elements:
                ocr_pages += 1
            for element in ocr_elements:
                sortable.append((element.reading_order, element))
            continue
        for block in page.get_text("blocks"):
            if len(block) < 5:
                continue
            x0, y0, x1, y1, block_text, *_rest = block
            cleaned = str(block_text).strip()
            if not cleaned:
                continue
            locator = PdfLocator(
                page_index=page_index,
                bbox_x0=round(float(x0), 3),
                bbox_y0=round(float(y0), 3),
                bbox_x1=round(float(x1), 3),
                bbox_y1=round(float(y1), 3),
            )
            sort_key = page_index * 10_000 + int(y0)
            sortable.append(
                (
                    sort_key,
                    TypedElement(
                        element_id=element_id(
                            content_hash,
                            sort_key,
                            ElementKind.PARAGRAPH,
                            locator,
                            cleaned,
                        ),
                        kind=ElementKind.PARAGRAPH,
                        text=cleaned,
                        reading_order=sort_key,
                        locator=locator,
                    ),
                )
            )

    repeated = detect_repeated_lines(page_lines)
    _cleaned_pages, removals = remove_repeated_lines(page_lines, repeated)
    if repeated:
        filtered: list[tuple[int, TypedElement]] = []
        for sort_key, element in sortable:
            if element.kind is ElementKind.PAGE_BREAK:
                filtered.append((sort_key, element))
                continue
            if element.text and element.text.strip() in repeated:
                continue
            filtered.append((sort_key, element))
        sortable = filtered

    elements: list[TypedElement] = []
    for order, (_sort_key, element) in enumerate(sorted(sortable, key=lambda item: item[0])):
        locator: SourceLocator = element.locator
        if isinstance(locator, OcrLocator):
            pass
        elements.append(
            TypedElement(
                **element.model_dump()
                | {
                    "reading_order": order,
                    "element_id": element_id(
                        content_hash,
                        order,
                        element.kind,
                        element.locator,
                        element.text,
                    ),
                }
            )
        )

    elements_tuple = tuple(elements)
    config_hash = ParseResult.stable_config_hash(PARSER_CONFIG_VERSION, CLEANING_POLICY_VERSION)
    return ParseResult(
        disposition=ParseDisposition.SUPPORTED,
        format=format_key,
        content_hash=content_hash,
        parser_version=PARSER_CONFIG_VERSION,
        cleaning_version=CLEANING_POLICY_VERSION,
        config_hash=config_hash,
        elements=elements_tuple,
        removals=removals,
        coverage=build_coverage(elements_tuple, removed=len(removals)),
        resource_metrics=ParserResourceMetrics(
            wall_seconds=time.monotonic() - started,
            pages_processed=document.page_count,
            ocr_pages=ocr_pages,
        ),
        detail="pdf parsed",
    )
