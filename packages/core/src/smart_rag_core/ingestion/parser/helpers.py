"""Shared helpers for deterministic parser output."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Iterable
from itertools import pairwise
from typing import NamedTuple, cast

from smart_rag_core.ingestion.parser.types import (
    CoverageAccounting,
    ElementKind,
    SourceLocator,
    TypedElement,
)
from smart_rag_core.text_constants import PARAGRAPH_DELIMITER

# PyMuPDF 1.25.5 span ``flags`` bit 4 (``TEXT_FONT_BOLD``).
PDF_TEXT_FONT_BOLD = 1 << 4
# PyMuPDF 1.25.5 span ``flags`` bit 3 (``TEXT_FONT_MONOSPACED``).
PDF_TEXT_FONT_MONOSPACED = 1 << 3
PDF_MONOSPACE_FONT_NAME = re.compile(
    r"mono|courier|consol|menlo|inconsolata|code", re.IGNORECASE
)
PDF_CODE_MAX_INDENT = 40
PDF_TABLE_CAPTION = re.compile(
    r"^(?:Table|TABLE)\s+[A-Z]?\d+(?:[.\-\u2010\u2013]\d+)*\b"
)
# Table geometry in PDF points, or in multiples of the table font size:
# lines whose tops differ by at most ROW_TOLERANCE share a row band; cells
# may overlap by CELL_OVERLAP; columns align within COLUMN_TOLERANCE; a
# caption sits within CAPTION_DISTANCE; a gap above MAX_GAP_RATIO ends the
# table; a lone aligned line within WRAP_GAP_RATIO continues it; when the
# gaps are mixed, a gap below ROW_PITCH_RATIO is a wrapped cell line.
PDF_TABLE_ROW_TOLERANCE = 2.0
PDF_TABLE_CELL_OVERLAP = 1.0
PDF_TABLE_COLUMN_TOLERANCE = 3.0
PDF_TABLE_CAPTION_DISTANCE = 60.0
PDF_TABLE_MAX_GAP_RATIO = 2.5
PDF_TABLE_WRAP_GAP_RATIO = 1.6
PDF_TABLE_ROW_PITCH_RATIO = 1.25
PDF_HEADING_MAX_WORDS = 12
PDF_HEADING_MAX_CHARS = 80
PDF_HEADING_SIZE_RATIO = 1.2
PDF_HEADING_MIN_SIZE = 11.0
LINE_END_HYPHENS = ("-", "\u2010", "\u00ad")
"""Line-end characters removed when they split one word across two lines.

ASCII hyphen-minus, U+2010 HYPHEN (the hyphen typeset books use), and
U+00AD SOFT HYPHEN. U+2011 NON-BREAKING HYPHEN is not listed: a line never
breaks after it, so a line-end U+2011 belongs to the text.
"""


class PdfTextBlock(NamedTuple):
    """One PDF text line from PyMuPDF ``get_text('dict')``.

    Vendor blocks often mix a title with following body copy. Emitting one
    line keeps short large or bold titles standalone for heading classification.

    Attributes:
        text: Concatenated span text for one line, without leading or
            trailing whitespace (code indentation is added later from
            ``text_x0``). For a table block, the Markdown pipe table.
        bbox: ``(x0, y0, x1, y1)`` from the vendor line, else the parent block.
        max_size: Largest span size on the line.
        bold: True when any span has ``TEXT_FONT_BOLD``.
        block_index: Position of the parent block in the page ``blocks`` list.
        monospace: True when every span with text uses a monospace font.
            After merging, it describes the last line of the paragraph.
        text_x0: X of the first visible character (monospace lines only).
        char_width: Average character width of the line (monospace only).
        table: True for a synthetic block built by ``detect_pdf_tables``.
    """

    text: str
    bbox: tuple[float, float, float, float]
    max_size: float
    bold: bool
    block_index: int
    monospace: bool = False
    text_x0: float = 0.0
    char_width: float = 0.0
    table: bool = False


def _union_pdf_bbox(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Return the axis-aligned union of two PDF boxes.

    Args:
        left: First ``(x0, y0, x1, y1)`` box.
        right: Second ``(x0, y0, x1, y1)`` box.

    Returns:
        Combined box.
    """

    return (
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    )


def join_pdf_lines(pending: PdfTextBlock, block: PdfTextBlock) -> str:
    """Join two paragraph lines without a mid-word break or a mid-block newline.

    A trailing hyphen from ``LINE_END_HYPHENS`` after a letter is removed
    when the next line starts with a lowercase letter, so ``com`` + U+2010 +
    ``plexity`` becomes ``complexity``. A real compound broken at its own
    hyphen at a line end loses that hyphen; hyphens inside a line are never
    touched. When the next line starts with anything else, the hyphen stays
    and the normal join applies. Lines from the same PyMuPDF block are
    separated by a space. Lines from different blocks use
    ``PARAGRAPH_DELIMITER`` so citation spans can still see paragraph
    boundaries. A table block is always its own paragraph. Two monospace
    (code) lines keep a newline when indentation changes, otherwise join
    with a space, and never lose a line-end hyphen; a switch between code
    and prose uses ``PARAGRAPH_DELIMITER``.

    Args:
        pending: Paragraph accumulated so far.
        block: Next paragraph line in reading order.

    Returns:
        Joined text. Neither input is mutated.
    """

    left = pending.text
    right = block.text
    if pending.table or block.table:
        return f"{left}{PARAGRAPH_DELIMITER}{right}"
    if pending.monospace and block.monospace:
        # Keep a newline when indentation changes (indented body or dedent).
        # Same-indent top-level lines stay space-joined so a phrase that the
        # vendor split across several monospace rows remains one substring;
        # ``phrase_is_present`` does not treat newlines as spaces.
        last = left.split("\n")[-1]
        if right.startswith(" ") or last.startswith(" "):
            return f"{left}\n{right}"
        return f"{left} {right}"
    if pending.monospace != block.monospace:
        return f"{left}{PARAGRAPH_DELIMITER}{right}"
    if (
        len(left) >= 2
        and left.endswith(LINE_END_HYPHENS)
        and left[-2].isalpha()
        and right[:1].islower()
    ):
        return f"{left[:-1]}{right}"
    if pending.block_index == block.block_index:
        return f"{left} {right}"
    return f"{left}{PARAGRAPH_DELIMITER}{right}"


def indent_pdf_code_lines(
    lines: tuple[tuple[ElementKind, PdfTextBlock], ...],
) -> tuple[tuple[ElementKind, PdfTextBlock], ...]:
    """Prefix monospace lines with spaces that rebuild their indentation.

    Each run of consecutive monospace paragraph lines is measured against
    the leftmost line of that run. The column offset is the x distance
    divided by the run's median character width, capped at
    ``PDF_CODE_MAX_INDENT``.

    Args:
        lines: Classified ``(kind, block)`` pairs in reading order.

    Returns:
        The same pairs; monospace paragraph lines carry leading spaces.
    """

    result = list(lines)
    index = 0
    while index < len(result):
        kind, block = result[index]
        if kind is not ElementKind.PARAGRAPH or not block.monospace:
            index += 1
            continue
        end = index
        while (
            end < len(result)
            and result[end][0] is ElementKind.PARAGRAPH
            and result[end][1].monospace
        ):
            end += 1
        run = [item[1] for item in result[index:end]]
        widths = sorted(item.char_width for item in run if item.char_width > 0)
        width = widths[len(widths) // 2] if widths else 0.0
        left = min(item.text_x0 for item in run)
        for offset, item in enumerate(run):
            columns = 0
            if width > 0:
                columns = min(
                    PDF_CODE_MAX_INDENT, max(0, round((item.text_x0 - left) / width))
                )
            result[index + offset] = (
                ElementKind.PARAGRAPH,
                item._replace(text=" " * columns + item.text),
            )
        index = end
    return tuple(result)


def merge_consecutive_pdf_paragraphs(
    lines: tuple[tuple[ElementKind, PdfTextBlock], ...],
) -> tuple[tuple[ElementKind, PdfTextBlock], ...]:
    """Join adjacent paragraph lines so heading lines stay standalone.

    Per-line ``get_text('dict')`` extraction keeps titles from being absorbed
    into body copy. Consecutive paragraphs are then concatenated so chunking
    can fill the 200-400 token band instead of emitting one passage per line.

    Args:
        lines: Classified ``(kind, block)`` pairs in reading order.

    Returns:
        The same order with consecutive ``PARAGRAPH`` blocks merged.
    """

    if not lines:
        return ()
    merged: list[tuple[ElementKind, PdfTextBlock]] = []
    pending: PdfTextBlock | None = None
    for kind, block in lines:
        if kind is ElementKind.PARAGRAPH:
            if pending is None:
                pending = block
                continue
            pending = PdfTextBlock(
                text=join_pdf_lines(pending, block),
                bbox=_union_pdf_bbox(pending.bbox, block.bbox),
                max_size=max(pending.max_size, block.max_size),
                bold=pending.bold or block.bold,
                block_index=block.block_index,
                monospace=block.monospace,
                text_x0=block.text_x0,
                char_width=block.char_width,
            )
            continue
        if pending is not None:
            merged.append((ElementKind.PARAGRAPH, pending))
            pending = None
        merged.append((kind, block))
    if pending is not None:
        merged.append((ElementKind.PARAGRAPH, pending))
    return tuple(merged)


def element_id(
    content_hash: str,
    reading_order: int,
    kind: str,
    locator: SourceLocator,
    text: str | None,
) -> str:
    """Build a stable element identifier for one parse replay.

    Args:
        content_hash: SHA-256 of source bytes.
        reading_order: Zero-based reading order index.
        kind: Element kind string.
        locator: Format-specific locator model.
        text: Optional element text.

    Returns:
        Deterministic lowercase hex identifier.
    """

    payload = f"{content_hash}|{reading_order}|{kind}|{locator.model_dump_json()}|{text or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def build_coverage(
    elements: tuple[TypedElement, ...], removed: int = 0
) -> CoverageAccounting:
    """Compute coverage accounting from emitted elements.

    Args:
        elements: Typed elements in reading order.
        removed: Count of removed boilerplate/header nodes.

    Returns:
        Coverage metrics with char coverage ratio.
    """

    text_elements = [
        element for element in elements if element.text and element.text.strip()
    ]
    media_only = [element for element in elements if element.media_only]
    unsupported = [
        element
        for element in elements
        if element.metadata.get("unsupported_region") is True
    ]
    total_chars = sum(len(element.text or "") for element in text_elements)
    source_chars = max(total_chars, 1)
    return CoverageAccounting(
        total_elements=len(elements),
        text_elements=len(text_elements),
        media_only_elements=len(media_only),
        removed_nodes=removed,
        unsupported_regions=len(unsupported),
        char_coverage_ratio=min(1.0, total_chars / source_chars),
    )


def namespace_seed(content_hash: str) -> uuid.UUID:
    """Derive a deterministic UUID namespace from content hash."""

    return uuid.UUID(hex=content_hash[:32])


def as_int(value: object) -> int:
    """Return ``int(value)`` for an untyped vendor scalar.

    Args:
        value: Vendor numeric value (int, float, or numeric string).

    Returns:
        The same integer conversion as ``int(value)`` for those scalars.

    Raises:
        TypeError: If ``value`` is not an int, float, or str.
        ValueError: If a string value is not a valid integer literal.
    """

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"value is not convertible to int: {type(value).__name__}")


def as_float(value: object) -> float:
    """Return ``float(value)`` for an untyped vendor scalar.

    Args:
        value: Vendor numeric value (int, float, or numeric string).

    Returns:
        The same float conversion as ``float(value)`` for those scalars.

    Raises:
        TypeError: If ``value`` is not an int, float, or str.
        ValueError: If a string value is not a valid float literal.
    """

    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"value is not convertible to float: {type(value).__name__}")


_VENDOR_ATTR_MISSING: object = object()


def vendor_attr(
    owner: object, name: str, default: object = _VENDOR_ATTR_MISSING
) -> object:
    """Return ``getattr(owner, name)`` with the same defaulting as builtins.

    Args:
        owner: Vendor module, document, page, or shape handle.
        name: Attribute name resolved at the call site.
        default: Optional fallback passed to ``getattr`` when not omitted.

    Returns:
        The attribute value, or ``default`` when provided and missing.
    """

    if default is _VENDOR_ATTR_MISSING:
        return getattr(owner, name)
    return getattr(owner, name, default)


def pdf_page_label(page: object) -> str:
    """Return the printed PDF page label for one PyMuPDF page.

    Uses ``Page.get_label()``. Empty when the file has no ``/PageLabels``
    entry for that page. Never used for element identity.

    Args:
        page: PyMuPDF page handle.

    Returns:
        Stripped label such as ``vii`` or ``179``, or ``""``.
    """

    getter = vendor_attr(page, "get_label", None)
    if not callable(getter):
        return ""
    raw = vendor_call(getter)
    if raw is None:
        return ""
    return str(raw).strip()


def vendor_call(func: object, /, *args: object) -> object:
    """Invoke one vendor callable with the original positional arguments.

    Args:
        func: Vendor method or function.
        *args: Positional arguments forwarded unchanged.

    Returns:
        Opaque vendor result.

    Raises:
        TypeError: If ``func`` is not callable.
    """

    if not callable(func):
        raise TypeError("vendor callable is not callable")
    return func(*args)


def vendor_items(value: object) -> list[object]:
    """Return a vendor collection as a list of opaque items.

    Args:
        value: Iterable vendor payload such as a page body or PDF blocks list.

    Returns:
        The same items in list form.

    Raises:
        TypeError: If ``value`` is not iterable (excluding str/bytes).
    """

    if isinstance(value, list):
        return cast(list[object], value)
    if isinstance(value, tuple):
        return list(cast(tuple[object, ...], value))
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return list(cast(Iterable[object], value))
    raise TypeError(f"vendor collection is not iterable: {type(value).__name__}")


def median_font_size(sizes: tuple[float, ...]) -> float:
    """Return the median font size from collected span sizes.

    Args:
        sizes: Positive span sizes from one page.

    Returns:
        Median size, or ``0.0`` when empty.
    """

    if not sizes:
        return 0.0
    ordered = tuple(sorted(sizes))
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _pdf_block_bbox(raw: object) -> tuple[float, float, float, float] | None:
    """Return a four-float bbox from a vendor mapping or sequence.

    Args:
        raw: Vendor ``bbox`` value.

    Returns:
        ``(x0, y0, x1, y1)`` or ``None`` when the payload is unusable.
    """

    items: list[object]
    if isinstance(raw, (list, tuple)):
        items = list(cast(list[object] | tuple[object, ...], raw))
    else:
        return None
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


def _span_is_bold(flags: object) -> bool:
    """Return whether a span ``flags`` integer has the bold bit.

    Args:
        flags: Vendor span flags.

    Returns:
        True when bit 4 is set.
    """

    try:
        return bool(as_int(flags) & PDF_TEXT_FONT_BOLD)
    except (TypeError, ValueError):
        return False


def _span_is_monospace(span_map: dict[object, object]) -> bool:
    """Return whether one span uses a monospace font.

    Args:
        span_map: Vendor span mapping with ``flags`` and ``font``.

    Returns:
        True when flag bit 3 is set or the font name looks monospace.
    """

    try:
        flagged = bool(as_int(span_map.get("flags", 0)) & PDF_TEXT_FONT_MONOSPACED)
    except (TypeError, ValueError):
        flagged = False
    return flagged or bool(
        PDF_MONOSPACE_FONT_NAME.search(str(span_map.get("font") or ""))
    )


def extract_pdf_text_blocks(
    raw: object,
) -> tuple[tuple[PdfTextBlock, ...], tuple[float, ...]]:
    """Walk PyMuPDF ``get_text('dict')`` into per-line text blocks and sizes.

    Image blocks (``type == 1``) are skipped. Unknown dict shapes return
    empty so the adapter can fall back to ``get_text('blocks')``. Lines are
    emitted separately so a large title is not absorbed into body copy.
    Lines whose text spans all use a monospace font are flagged
    ``monospace`` with ``text_x0`` and ``char_width`` so code indentation
    can be rebuilt.

    Args:
        raw: Vendor dictionary from ``page.get_text('dict')``.

    Returns:
        Text blocks and every numeric span size used for the page median.
    """

    if not isinstance(raw, dict):
        return (), ()
    mapping = cast(dict[object, object], raw)
    blocks_raw = mapping.get("blocks")
    if blocks_raw is None:
        return (), ()
    try:
        blocks = vendor_items(blocks_raw)
    except TypeError:
        return (), ()
    collected: list[PdfTextBlock] = []
    sizes: list[float] = []
    for block_index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        block_map = cast(dict[object, object], block)
        kind = block_map.get("type", 0)
        try:
            if as_int(kind) == 1:
                continue
        except (TypeError, ValueError):
            continue
        block_bbox = _pdf_block_bbox(block_map.get("bbox"))
        if block_bbox is None:
            continue
        lines_raw = block_map.get("lines")
        if lines_raw is None:
            continue
        try:
            lines = vendor_items(lines_raw)
        except TypeError:
            continue
        for line in lines:
            if not isinstance(line, dict):
                continue
            line_map = cast(dict[object, object], line)
            spans_raw = line_map.get("spans")
            if spans_raw is None:
                continue
            try:
                spans = vendor_items(spans_raw)
            except TypeError:
                continue
            line_parts: list[str] = []
            max_size = 0.0
            bold = False
            text_spans = 0
            mono_spans = 0
            for span in spans:
                if not isinstance(span, dict):
                    continue
                span_map = cast(dict[object, object], span)
                text = str(span_map.get("text") or "")
                if text:
                    line_parts.append(text)
                if text.strip():
                    text_spans += 1
                    if _span_is_monospace(span_map):
                        mono_spans += 1
                size_raw = span_map.get("size")
                if size_raw is not None:
                    try:
                        size = as_float(size_raw)
                    except (TypeError, ValueError):
                        size = 0.0
                    if size > 0:
                        sizes.append(size)
                        if size > max_size:
                            max_size = size
                if _span_is_bold(span_map.get("flags", 0)):
                    bold = True
            raw_line = "".join(line_parts).rstrip()
            cleaned = raw_line.strip()
            if not cleaned:
                continue
            bbox = _pdf_block_bbox(line_map.get("bbox")) or block_bbox
            monospace = text_spans > 0 and mono_spans == text_spans
            text_x0 = 0.0
            char_width = 0.0
            if monospace:
                char_width = (bbox[2] - bbox[0]) / len(raw_line)
                leading = len(raw_line) - len(raw_line.lstrip())
                text_x0 = bbox[0] + leading * char_width
            collected.append(
                PdfTextBlock(
                    text=cleaned,
                    bbox=bbox,
                    max_size=max_size,
                    bold=bold,
                    block_index=block_index,
                    monospace=monospace,
                    text_x0=text_x0,
                    char_width=char_width,
                )
            )
    return tuple(collected), tuple(sizes)


class PdfTable(NamedTuple):
    """One table rebuilt from PDF line geometry.

    Attributes:
        members: Indexes of the page lines that belong to the table.
        columns: Left x of each column, in points.
        block: Synthetic line whose text is the Markdown pipe table.
    """

    members: frozenset[int]
    columns: tuple[float, ...]
    block: PdfTextBlock


def _pdf_row_bands(lines: tuple[PdfTextBlock, ...]) -> list[list[int]]:
    """Group line indexes into row bands by top y.

    Args:
        lines: Page lines in extraction order.

    Returns:
        Bands from top to bottom; each band lists line indexes by x0.
    """

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
    """Return whether a band holds two or more side-by-side cells.

    Monospace-only bands are code, never table cells.

    Args:
        lines: Page lines.
        band: Line indexes sorted by x0.

    Returns:
        True for at least two non-overlapping lines that are not all code.
    """

    if len(band) < 2 or all(lines[index].monospace for index in band):
        return False
    return all(
        lines[band[position]].bbox[0]
        >= lines[band[position - 1]].bbox[2] - PDF_TABLE_CELL_OVERLAP
        for position in range(1, len(band))
    )


def _pdf_aligned(x0: float, columns: tuple[float, ...]) -> bool:
    """Return whether ``x0`` starts at one of the column positions.

    Args:
        x0: Line left x.
        columns: Column left x values.

    Returns:
        True within ``PDF_TABLE_COLUMN_TOLERANCE``.
    """

    return any(abs(x0 - column) <= PDF_TABLE_COLUMN_TOLERANCE for column in columns)


def _pdf_column_index(columns: tuple[float, ...], x0: float) -> int:
    """Return the column a line belongs to: the last column starting at or left of it.

    Args:
        columns: Column left x values in order.
        x0: Line left x.

    Returns:
        Zero-based column index.
    """

    index = 0
    for position, column in enumerate(columns):
        if column <= x0 + PDF_TABLE_COLUMN_TOLERANCE:
            index = position
    return index


def _pdf_table_regions(
    lines: tuple[PdfTextBlock, ...],
    bands: list[list[int]],
) -> list[tuple[list[list[int]], tuple[float, ...]]]:
    """Find runs of row bands that look like one table.

    A region starts at a multi-column band and continues through further
    multi-column bands and lone lines aligned with a column (wrapped
    cells). It ends at a large gap or at any other line.

    Args:
        lines: Page lines.
        bands: Output of ``_pdf_row_bands``.

    Returns:
        ``(region bands, column x values)`` for regions with at least two
        multi-column bands.
    """

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
            if (
                _pdf_aligned(lines[band[0]].bbox[0], columns)
                and gap <= PDF_TABLE_WRAP_GAP_RATIO * size
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


def _join_pdf_cell_text(left: str, right: str) -> str:
    """Join a wrapped cell line onto the cell text.

    Args:
        left: Cell text so far (may be empty).
        right: Next line of the same cell.

    Returns:
        Joined text; a letter-hyphen break before a lowercase letter is
        rejoined like body text.
    """

    if not left:
        return right
    if (
        len(left) >= 2
        and left.endswith(LINE_END_HYPHENS)
        and left[-2].isalpha()
        and right[:1].islower()
    ):
        return f"{left[:-1]}{right}"
    return f"{left} {right}"


def _pdf_table_rows(
    lines: tuple[PdfTextBlock, ...],
    region: list[list[int]],
    columns: tuple[float, ...],
) -> list[list[str]]:
    """Assemble cell text per row.

    When the gaps between bands are mixed, a gap below
    ``PDF_TABLE_ROW_PITCH_RATIO`` times the median font size is a wrapped
    line of the current row; otherwise every band is its own row.

    Args:
        lines: Page lines.
        region: Bands of one table.
        columns: Column left x values.

    Returns:
        Rows of cell strings, one string per column (empty when absent).
    """

    size = median_font_size(
        tuple(lines[index].max_size for band in region for index in band)
    )
    tops = [lines[band[0]].bbox[1] for band in region]
    gaps = [lower - upper for upper, lower in pairwise(tops)]
    limit = PDF_TABLE_ROW_PITCH_RATIO * size
    mixed = any(gap >= limit for gap in gaps)
    rows: list[list[str]] = []
    for position, band in enumerate(region):
        if not rows or not (mixed and gaps[position - 1] < limit):
            rows.append([""] * len(columns))
        row = rows[-1]
        for index in band:
            column = _pdf_column_index(columns, lines[index].bbox[0])
            row[column] = _join_pdf_cell_text(row[column], lines[index].text)
    return rows


def _pdf_pipe_row(cells: list[str]) -> str:
    """Render one Markdown pipe-table row.

    Args:
        cells: Cell strings.

    Returns:
        ``| a | b |`` with literal pipes escaped.
    """

    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def _pdf_table_markdown(rows: list[list[str]]) -> str:
    """Render rows as a Markdown pipe table; the first row is the header.

    A reading-order plain projection follows the pipe table so a phrase that
    spans adjacent cells (joined by spaces in the printed row) remains a
    single substring. ``phrase_is_present`` does not treat `` | `` as a space.

    Args:
        rows: At least two rows of equal width.

    Returns:
        Header, ``| --- |`` separator, body rows, then a blank line and one
        space-joined plain line per row.
    """

    width = len(rows[0])
    pipe = "\n".join(
        [
            _pdf_pipe_row(rows[0]),
            _pdf_pipe_row(["---"] * width),
            *(_pdf_pipe_row(row) for row in rows[1:]),
        ]
    )
    plain = "\n".join(" ".join(row) for row in rows)
    return f"{pipe}{PARAGRAPH_DELIMITER}{plain}"


def detect_pdf_tables(
    lines: tuple[PdfTextBlock, ...],
    *,
    previous_columns: tuple[float, ...] = (),
) -> tuple[PdfTable, ...]:
    """Rebuild captioned tables from one page's line geometry.

    A region becomes a table when a line matching ``PDF_TABLE_CAPTION``
    sits within ``PDF_TABLE_CAPTION_DISTANCE`` above or below it, or when
    it is the first region on the page and its columns match the last
    table of the previous page (a continued table). Regions without either
    signal (two-column text, indexes, glossaries) are left unchanged.

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
        captioned = any(
            index not in members
            and PDF_TABLE_CAPTION.match(line.text) is not None
            and (
                0.0 <= top - line.bbox[3] <= PDF_TABLE_CAPTION_DISTANCE
                or 0.0 <= line.bbox[1] - bottom <= PDF_TABLE_CAPTION_DISTANCE
            )
            for index, line in enumerate(lines)
        )
        continued = (
            not tables
            and len(previous_columns) == len(columns)
            and all(
                abs(left - right) <= PDF_TABLE_COLUMN_TOLERANCE
                for left, right in zip(previous_columns, columns, strict=True)
            )
        )
        if not (captioned or continued):
            continue
        rows = _pdf_table_rows(lines, region, columns)
        if len(rows) < 2:
            continue
        tables.append(
            PdfTable(
                members=members,
                columns=columns,
                block=PdfTextBlock(
                    text=_pdf_table_markdown(rows),
                    bbox=(
                        min(lines[index].bbox[0] for index in members),
                        top,
                        max(lines[index].bbox[2] for index in members),
                        bottom,
                    ),
                    max_size=max(lines[index].max_size for index in members),
                    bold=False,
                    block_index=lines[min(members)].block_index,
                    table=True,
                ),
            )
        )
    return tuple(tables)


def _sentence_like_pdf_text(text: str) -> bool:
    """Return whether text looks like a body sentence, not a heading.

    Args:
        text: Block text.

    Returns:
        True when the block should stay a paragraph.
    """

    stripped = text.strip()
    words = stripped.split()
    if len(words) >= 10:
        return True
    if len(stripped) > 72 and ("." in stripped or "。" in stripped):
        return True
    if stripped.endswith((".", "?", "!", "。")) and len(words) >= 6:
        return True
    return False


def classify_pdf_text_block(
    *,
    text: str,
    max_size: float,
    median_size: float,
    bold: bool,
) -> ElementKind:
    """Classify one PDF text block as heading or paragraph.

    Conservative: short standalone large titles become headings. Same-size
    bold labels and uncertain blocks stay paragraphs so live books do not
    emit one passage per bold line.

    Args:
        text: Block text.
        max_size: Largest span size in the block.
        median_size: Median span size on the page.
        bold: True when any span is flagged bold. Same-size bold is not
            enough without a size jump; it remains available for callers that
            still pass the flag for diagnostics.

    Returns:
        ``HEADING`` or ``PARAGRAPH``.
    """

    stripped = text.strip()
    if not stripped or _sentence_like_pdf_text(stripped):
        return ElementKind.PARAGRAPH
    words = stripped.split()
    if len(words) > PDF_HEADING_MAX_WORDS or len(stripped) > PDF_HEADING_MAX_CHARS:
        return ElementKind.PARAGRAPH
    large = median_size > 0 and max_size >= max(
        PDF_HEADING_MIN_SIZE, median_size * PDF_HEADING_SIZE_RATIO
    )
    if large:
        return ElementKind.HEADING
    _ = bold
    return ElementKind.PARAGRAPH
