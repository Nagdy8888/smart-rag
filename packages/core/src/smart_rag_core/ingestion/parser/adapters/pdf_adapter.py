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
    indent_pdf_code_lines,
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
from smart_rag_core.ingestion.parser.pdf_layout import (
    PdfFigureRef,
    PdfTable,
    detect_pdf_tables,
    extract_pdf_figures,
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
    previous_table_columns: tuple[float, ...] = ()
    previous_caption = ""
    for page_index in range(page_count):
        carried_columns = previous_table_columns
        previous_table_columns = ()
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
        page_dict = vendor_call(vendor_attr(page, "get_text"), "dict")
        dict_blocks, sizes = extract_pdf_text_blocks(page_dict)
        median_size = median_font_size(sizes)
        if dict_blocks:
            tables = detect_pdf_tables(dict_blocks, previous_columns=carried_columns)
            if tables:
                previous_table_columns = tables[-1].columns
            table_at = {min(table.members): table for table in tables}
            in_table = frozenset(index for table in tables for index in table.members)
            classified: list[tuple[ElementKind, PdfTextBlock]] = []
            for index, block in enumerate(dict_blocks):
                if index in table_at:
                    _append_pdf_table(
                        sortable,
                        content_hash=content_hash,
                        page_index=page_index,
                        table=table_at[index],
                        caption=table_at[index].caption or previous_caption,
                    )
                    if table_at[index].caption:
                        previous_caption = table_at[index].caption
                    continue
                if index in in_table:
                    continue
                cleaned = block.text.strip()
                if not cleaned:
                    continue
                kind = (
                    ElementKind.PARAGRAPH
                    if block.monospace
                    else classify_pdf_text_block(
                        text=cleaned,
                        max_size=block.max_size,
                        median_size=median_size,
                        bold=block.bold,
                    )
                )
                classified.append((kind, block))
            classified = list(indent_pdf_code_lines(tuple(classified)))
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
            for figure in extract_pdf_figures(page_dict):
                _append_pdf_figure(
                    sortable,
                    content_hash=content_hash,
                    page_index=page_index,
                    figure=figure,
                    caption=_nearest_caption(dict_blocks, figure.bbox),
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


def _typed_kind(text: str) -> str:
    """Infer a scalar kind for one PDF table cell."""

    stripped = text.strip().replace(",", "")
    if stripped.startswith("-"):
        body = stripped[1:]
    else:
        body = stripped
    if body.isdigit():
        return "integer"
    try:
        float(stripped)
    except ValueError:
        return "string"
    if any(mark in stripped for mark in (".", "e", "E")):
        return "float"
    return "string"


def _locator_for(page_index: int, bbox: tuple[float, float, float, float]) -> PdfLocator:
    """Build a rounded PDF locator for one box."""

    x0, y0, x1, y1 = bbox
    return PdfLocator(
        page_index=page_index,
        bbox_x0=round(x0, 3),
        bbox_y0=round(y0, 3),
        bbox_x1=round(x1, 3),
        bbox_y1=round(y1, 3),
    )


def _append_pdf_table(
    sortable: list[tuple[int, TypedElement]],
    *,
    content_hash: str,
    page_index: int,
    table: PdfTable,
    caption: str,
) -> None:
    """Emit one table wrapper plus header and body cells."""

    table_name = caption.strip() or f"page-{page_index + 1}-table"
    wrapper_locator = _locator_for(page_index, table.bbox)
    sort_key = page_index * 10_000 + as_int(table.bbox[1])
    sortable.append(
        (
            sort_key,
            TypedElement(
                element_id=element_id(
                    content_hash,
                    sort_key,
                    ElementKind.TABLE,
                    wrapper_locator,
                    table_name,
                ),
                kind=ElementKind.TABLE,
                text=table_name,
                reading_order=sort_key,
                locator=wrapper_locator,
                metadata={"table_name": table_name},
            ),
        )
    )
    for cell in table.cells:
        locator = _locator_for(page_index, cell.bbox)
        kind = (
            ElementKind.TABLE_HEADER if cell.row_index == 0 else ElementKind.TABLE_CELL
        )
        cell_key = sort_key + cell.row_index * 20 + cell.column_index
        sortable.append(
            (
                cell_key,
                TypedElement(
                    element_id=element_id(
                        content_hash,
                        cell_key,
                        kind,
                        locator,
                        cell.text,
                    ),
                    kind=kind,
                    text=cell.text,
                    reading_order=cell_key,
                    locator=locator,
                    metadata={
                        "table_name": table_name,
                        "row_index": cell.row_index,
                        "column_index": cell.column_index,
                        "typed_value_kind": _typed_kind(cell.text),
                    },
                ),
            )
        )


def _nearest_caption(
    lines: tuple[PdfTextBlock, ...],
    bbox: tuple[float, float, float, float],
) -> str:
    """Return the closest short line within 60 points of a figure."""

    best = ""
    best_gap = 60.0
    for line in lines:
        if len(line.text) > 160:
            continue
        gap_above = bbox[1] - line.bbox[3]
        gap_below = line.bbox[1] - bbox[3]
        gap = gap_above if gap_above >= 0 else gap_below
        if 0.0 <= gap <= best_gap:
            best = line.text
            best_gap = gap
    return best


def _append_pdf_figure(
    sortable: list[tuple[int, TypedElement]],
    *,
    content_hash: str,
    page_index: int,
    figure: PdfFigureRef,
    caption: str,
) -> None:
    """Emit one figure locator. Pixels are stored later, outside the sandbox."""

    locator = _locator_for(page_index, figure.bbox)
    sort_key = page_index * 10_000 + as_int(figure.bbox[1])
    figure_id = element_id(
        content_hash,
        sort_key,
        ElementKind.FIGURE,
        locator,
        figure.content_hash,
    )
    text = caption.strip() or None
    sortable.append(
        (
            sort_key,
            TypedElement(
                element_id=figure_id,
                kind=ElementKind.FIGURE,
                text=text,
                reading_order=sort_key,
                locator=locator,
                media_only=text is None,
                metadata={
                    "figure_id": figure_id,
                    "xref": figure.xref,
                    "width": figure.width,
                    "height": figure.height,
                    "content_hash": figure.content_hash,
                },
            ),
        )
    )
