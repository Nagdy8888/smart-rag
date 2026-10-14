"""PDF table geometry and figure locators. No model calls."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from itertools import pairwise
from typing import NamedTuple, cast

from smart_rag_core.ingestion.parser.helpers import (
    LINE_END_HYPHENS,
    PDF_FIGURE_MIN_PIXELS,
    PDF_TABLE_CAPTION,
    PDF_TABLE_CAPTION_DISTANCE,
    PDF_TABLE_CELL_OVERLAP,
    PDF_TABLE_COLUMN_TOLERANCE,
    PDF_TABLE_MAX_GAP_RATIO,
    PDF_TABLE_ROW_PITCH_RATIO,
    PDF_TABLE_ROW_TOLERANCE,
    PDF_TABLE_WRAP_GAP_RATIO,
    PdfTextBlock,
    as_float,
    as_int,
    median_font_size,
    vendor_items,
)


class PdfTableCell(NamedTuple):
    """One reconstructed table cell.

    Attributes:
        text: Cell text with wrapped lines joined.
        bbox: Union of the source line boxes.
        row_index: Zero-based row. Row 0 is the header.
        column_index: Zero-based column.
    """

    text: str
    bbox: tuple[float, float, float, float]
    row_index: int
    column_index: int


class PdfTable(NamedTuple):
    """One captioned or continued table rebuilt from line geometry.

    Attributes:
        members: Indexes of the page lines that belong to the table.
        columns: Left x of each column, in points.
        caption: Nearby caption text, or empty for a continuation.
        cells: Header and body cells in row-major order.
        bbox: Union of member line boxes.
    """

    members: frozenset[int]
    columns: tuple[float, ...]
    caption: str
    cells: tuple[PdfTableCell, ...]
    bbox: tuple[float, float, float, float]


class PdfFigureRef(NamedTuple):
    """One image block large enough to keep. Bytes stay out of the tree.

    Attributes:
        bbox: Page box in PDF points.
        xref: Image xref, or 0 when the vendor dict omitted it.
        width: Pixel width.
        height: Pixel height.
        content_hash: SHA-256 of the identity fields, or of image bytes
            when the dict included them. The bytes themselves are not kept.
    """

    bbox: tuple[float, float, float, float]
    xref: int
    width: int
    height: int
    content_hash: str


def _pdf_row_bands(lines: tuple[PdfTextBlock, ...]) -> list[list[int]]:
    """Group line indexes into row bands by top y."""

    order = sorted(
        range(len(lines)),
        key=lambda index: (lines[index].bbox[1], lines[index].bbox[0]),
    )
    bands: list[list[int]] = []
    for index in order:
        if (
            bands
            and lines[index].bbox[1] - lines[bands[-1][0]].bbox[1]
            <= PDF_TABLE_ROW_TOLERANCE
        ):
            bands[-1].append(index)
        else:
            bands.append([index])
    return [sorted(band, key=lambda index: lines[index].bbox[0]) for band in bands]


def _pdf_band_is_multi_column(lines: tuple[PdfTextBlock, ...], band: list[int]) -> bool:
    """Return whether a band holds two or more side-by-side non-code cells."""

    if len(band) < 2 or all(lines[index].monospace for index in band):
        return False
    return all(
        lines[band[position]].bbox[0]
        >= lines[band[position - 1]].bbox[2] - PDF_TABLE_CELL_OVERLAP
        for position in range(1, len(band))
    )


def _pdf_aligned(x0: float, columns: tuple[float, ...]) -> bool:
    """Return whether ``x0`` starts at one of the column positions."""

    return any(abs(x0 - column) <= PDF_TABLE_COLUMN_TOLERANCE for column in columns)


def _pdf_column_index(columns: tuple[float, ...], x0: float) -> int:
    """Return the last column starting at or left of ``x0``."""

    index = 0
    for position, column in enumerate(columns):
        if column <= x0 + PDF_TABLE_COLUMN_TOLERANCE:
            index = position
    return index


def _pdf_table_regions(
    lines: tuple[PdfTextBlock, ...],
    bands: list[list[int]],
) -> list[tuple[list[list[int]], tuple[float, ...]]]:
    """Find runs of row bands that look like one table."""

    regions: list[tuple[list[list[int]], tuple[float, ...]]] = []
    start = 0
    while start < len(bands):
        if not _pdf_band_is_multi_column(lines, bands[start]):
            start += 1
            continue
        columns = tuple(lines[index].bbox[0] for index in bands[start])
        size = max(lines[index].max_size for index in bands[start]) or 1.0
        end = start + 1
        while end < len(bands):
            band = bands[end]
            gap = lines[band[0]].bbox[1] - lines[bands[end - 1][0]].bbox[1]
            if gap > PDF_TABLE_MAX_GAP_RATIO * size:
                break
            if _pdf_band_is_multi_column(lines, band):
                if len(band) > len(columns):
                    columns = tuple(lines[index].bbox[0] for index in band)
                end += 1
                continue
            if _pdf_aligned(lines[band[0]].bbox[0], columns) and (
                gap <= PDF_TABLE_WRAP_GAP_RATIO * size
            ):
                end += 1
                continue
            break
        region = bands[start:end]
        if sum(1 for band in region if _pdf_band_is_multi_column(lines, band)) >= 2:
            regions.append((region, columns))
            start = end
        else:
            start += 1
    return regions


def _join_cell(left: str, right: str) -> str:
    """Join a wrapped cell line, repairing a letter-hyphen break."""

    if not left:
        return right
    if (
        len(left) >= 2
        and left[-1] in LINE_END_HYPHENS
        and left[-2].isalpha()
        and right[:1].islower()
    ):
        return f"{left[:-1]}{right}"
    return f"{left} {right}"


def _union_bbox(
    boxes: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Return the axis-aligned union of one or more boxes."""

    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _pdf_table_cells(
    lines: tuple[PdfTextBlock, ...],
    region: list[list[int]],
    columns: tuple[float, ...],
) -> tuple[PdfTableCell, ...]:
    """Assemble cells. The first row is the header."""

    size = median_font_size(
        tuple(lines[index].max_size for band in region for index in band)
    )
    tops = [lines[band[0]].bbox[1] for band in region]
    gaps = [lower - upper for upper, lower in pairwise(tops)]
    limit = PDF_TABLE_ROW_PITCH_RATIO * (size or 1.0)
    mixed = any(gap >= limit for gap in gaps)
    rows: list[list[tuple[str, list[tuple[float, float, float, float]]]]] = []
    for position, band in enumerate(region):
        if not rows or not (mixed and position > 0 and gaps[position - 1] < limit):
            rows.append([("", []) for _ in columns])
        row = rows[-1]
        for index in band:
            column = _pdf_column_index(columns, lines[index].bbox[0])
            text, boxes = row[column]
            row[column] = (
                _join_cell(text, lines[index].text),
                [*boxes, lines[index].bbox],
            )
    cells: list[PdfTableCell] = []
    for row_index, row in enumerate(rows):
        for column_index, (text, boxes) in enumerate(row):
            if not boxes:
                continue
            cells.append(
                PdfTableCell(
                    text=text,
                    bbox=_union_bbox(boxes),
                    row_index=row_index,
                    column_index=column_index,
                )
            )
    return tuple(cells)


def detect_pdf_tables(
    lines: tuple[PdfTextBlock, ...],
    *,
    previous_columns: tuple[float, ...] = (),
) -> tuple[PdfTable, ...]:
    """Rebuild captioned tables from one page's line geometry.

    A region becomes a table when a ``Table N`` caption sits within
    ``PDF_TABLE_CAPTION_DISTANCE`` above or below it, or when it is the
    first region on the page and its columns match the previous page.
    Two-column prose, indexes, and glossaries stay lines.

    Args:
        lines: Page lines in extraction order.
        previous_columns: Column x values of the last table on the
            previous page, or empty.

    Returns:
        Tables in top-to-bottom order.
    """

    tables: list[PdfTable] = []
    for region, columns in _pdf_table_regions(lines, _pdf_row_bands(lines)):
        members = frozenset(index for band in region for index in band)
        top = min(lines[index].bbox[1] for index in members)
        bottom = max(lines[index].bbox[3] for index in members)
        caption = ""
        for index, line in enumerate(lines):
            if index in members or PDF_TABLE_CAPTION.match(line.text) is None:
                continue
            above = 0.0 <= top - line.bbox[3] <= PDF_TABLE_CAPTION_DISTANCE
            below = 0.0 <= line.bbox[1] - bottom <= PDF_TABLE_CAPTION_DISTANCE
            if above or below:
                caption = line.text
                break
        continued = (
            not tables
            and len(previous_columns) == len(columns)
            and all(
                abs(left - right) <= PDF_TABLE_COLUMN_TOLERANCE
                for left, right in zip(previous_columns, columns, strict=True)
            )
        )
        if not (caption or continued):
            continue
        cells = _pdf_table_cells(lines, region, columns)
        if len({cell.row_index for cell in cells}) < 2:
            continue
        tables.append(
            PdfTable(
                members=members,
                columns=columns,
                caption=caption,
                cells=cells,
                bbox=(
                    min(lines[index].bbox[0] for index in members),
                    top,
                    max(lines[index].bbox[2] for index in members),
                    bottom,
                ),
            )
        )
    return tuple(tables)


def _bbox_from(raw: object) -> tuple[float, float, float, float] | None:
    """Parse a four-number vendor box."""

    if not isinstance(raw, (list, tuple)):
        return None
    items = cast(Sequence[object], raw)
    if len(items) < 4:
        return None
    try:
        return (
            as_float(items[0]),
            as_float(items[1]),
            as_float(items[2]),
            as_float(items[3]),
        )
    except (TypeError, ValueError):
        return None


def extract_pdf_figures(raw: object) -> tuple[PdfFigureRef, ...]:
    """Record image blocks above the minimum pixel size.

    Args:
        raw: Vendor dictionary from ``page.get_text('dict')``.

    Returns:
        Figure locators. Image bytes are hashed when present and then
        discarded. Tiny decorations are skipped.
    """

    if not isinstance(raw, dict):
        return ()
    mapping = cast(dict[object, object], raw)
    blocks_raw = mapping.get("blocks")
    if blocks_raw is None:
        return ()
    try:
        blocks = vendor_items(blocks_raw)
    except TypeError:
        return ()
    figures: list[PdfFigureRef] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_map = cast(dict[object, object], block)
        try:
            if as_int(block_map.get("type", 0)) != 1:
                continue
        except (TypeError, ValueError):
            continue
        bbox = _bbox_from(block_map.get("bbox"))
        if bbox is None:
            continue
        try:
            width = as_int(block_map.get("width", 0))
            height = as_int(block_map.get("height", 0))
        except (TypeError, ValueError):
            continue
        if width * height < PDF_FIGURE_MIN_PIXELS:
            continue
        xref = 0
        for key in ("xref", "number"):
            try:
                xref = as_int(block_map.get(key, 0))
            except (TypeError, ValueError):
                xref = 0
            if xref:
                break
        image = block_map.get("image")
        if isinstance(image, (bytes, bytearray)) and image:
            digest = hashlib.sha256(bytes(image)).hexdigest()
        else:
            identity = f"{xref}|{width}|{height}|{bbox[0]:.3f}|{bbox[1]:.3f}"
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        figures.append(
            PdfFigureRef(
                bbox=bbox,
                xref=xref,
                width=width,
                height=height,
                content_hash=digest,
            )
        )
    return tuple(figures)
