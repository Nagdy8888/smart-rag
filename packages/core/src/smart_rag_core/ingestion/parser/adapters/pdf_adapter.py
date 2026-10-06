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
from smart_rag_core.ingestion.parser.helpers import (
    PdfTextBlock,
    as_float,
    as_int,
    build_coverage,
    classify_pdf_text_block,
    element_id,
    extract_pdf_text_blocks,
    median_font_size,
    merge_consecutive_pdf_paragraphs,
    pdf_page_label,
    vendor_attr,
    vendor_call,
    vendor_items,
)
from smart_rag_core.ingestion.parser.limits import (
    CLEANING_POLICY_VERSION,
    PDF_MAX_PAGES,
    PDF_PARSER_VERSION,
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
    """Parse a PDF into typed elements with page locators and OCR fallback.

    Args:
        path: Local PDF path.
        content_hash: SHA-256 of source bytes.
        format_key: Canonical format key, ``pdf``.

    Returns:
        Typed parse. ``page_labels`` is aligned with zero-based
        ``page_index``. Labels are not stored on element locators, so
        element IDs stay stable across unlabeled and labeled files.
    """

    started = time.monotonic()
    try:
        document = fitz.open(path)
    except RuntimeError as exc:
        if "password" in str(exc).lower():
            raise ParserEncryptedError("password-protected PDF") from exc
        raise
    if document.needs_pass:
        raise ParserEncryptedError("password-protected PDF")
    page_count = as_int(vendor_attr(document, "page_count"))
    if page_count > PDF_MAX_PAGES:
        raise ParserLimitExceeded("pages", f"page count {page_count}")

    page_lines: list[list[str]] = []
    page_labels: list[str] = []
    sortable: list[tuple[int, TypedElement]] = []
    ocr_pages = 0
    for page_index in range(page_count):
        page = document.load_page(page_index)
        page_labels.append(pdf_page_label(page))
        text = str(vendor_call(vendor_attr(page, "get_text"), "text"))
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
        dict_blocks, sizes = extract_pdf_text_blocks(
            vendor_call(vendor_attr(page, "get_text"), "dict")
        )
        median_size = median_font_size(sizes)
        if dict_blocks:
            classified: list[tuple[ElementKind, PdfTextBlock]] = []
            for block in dict_blocks:
                cleaned = block.text.strip()
                if not cleaned:
                    continue
                kind = classify_pdf_text_block(
                    text=cleaned,
                    max_size=block.max_size,
                    median_size=median_size,
                    bold=block.bold,
                )
                classified.append((kind, block))
            for kind, block in merge_consecutive_pdf_paragraphs(tuple(classified)):
                cleaned = block.text.strip()
                x0, y0, x1, y1 = block.bbox
                locator = PdfLocator(
                    page_index=page_index,
                    bbox_x0=round(x0, 3),
                    bbox_y0=round(y0, 3),
                    bbox_x1=round(x1, 3),
                    bbox_y1=round(y1, 3),
                )
                sort_key = page_index * 10_000 + as_int(y0)
                sortable.append(
                    (
                        sort_key,
                        TypedElement(
                            element_id=element_id(
                                content_hash,
                                sort_key,
                                kind,
                                locator,
                                cleaned,
                            ),
                            kind=kind,
                            text=cleaned,
                            reading_order=sort_key,
                            locator=locator,
                        ),
                    )
                )
            continue
        for block in vendor_items(vendor_call(vendor_attr(page, "get_text"), "blocks")):
            parts = vendor_items(block)
            if len(parts) < 5:
                continue
            x0, y0, x1, y1, block_text = (
                parts[0],
                parts[1],
                parts[2],
                parts[3],
                parts[4],
            )
            cleaned = str(block_text).strip()
            if not cleaned:
                continue
            locator = PdfLocator(
                page_index=page_index,
                bbox_x0=round(as_float(x0), 3),
                bbox_y0=round(as_float(y0), 3),
                bbox_x1=round(as_float(x1), 3),
                bbox_y1=round(as_float(y1), 3),
            )
            sort_key = page_index * 10_000 + as_int(y0)
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
    for order, (_sort_key, element) in enumerate(
        sorted(sortable, key=lambda item: item[0])
    ):
        locator: SourceLocator = element.locator
        if isinstance(locator, OcrLocator):
            pass
        elements.append(
            element.model_copy(
                update={
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
    config_hash = ParseResult.stable_config_hash(
        PDF_PARSER_VERSION, CLEANING_POLICY_VERSION
    )
    return ParseResult(
        disposition=ParseDisposition.SUPPORTED,
        format=format_key,
        content_hash=content_hash,
        parser_version=PDF_PARSER_VERSION,
        cleaning_version=CLEANING_POLICY_VERSION,
        config_hash=config_hash,
        elements=elements_tuple,
        page_labels=tuple(page_labels),
        removals=removals,
        coverage=build_coverage(elements_tuple, removed=len(removals)),
        resource_metrics=ParserResourceMetrics(
            wall_seconds=time.monotonic() - started,
            pages_processed=page_count,
            ocr_pages=ocr_pages,
        ),
        detail="pdf parsed",
    )
