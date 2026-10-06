"""Shared helpers for deterministic parser output."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
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
        text: Concatenated span text for one line.
        bbox: ``(x0, y0, x1, y1)`` from the vendor line, else the parent block.
        max_size: Largest span size on the line.
        bold: True when any span has ``TEXT_FONT_BOLD``.
        block_index: Position of the parent block in the page ``blocks`` list.
    """

    text: str
    bbox: tuple[float, float, float, float]
    max_size: float
    bold: bool
    block_index: int


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
    boundaries.

    Args:
        pending: Paragraph accumulated so far.
        block: Next paragraph line in reading order.

    Returns:
        Joined text. Neither input is mutated.
    """

    left = pending.text
    right = block.text
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


def extract_pdf_text_blocks(
    raw: object,
) -> tuple[tuple[PdfTextBlock, ...], tuple[float, ...]]:
    """Walk PyMuPDF ``get_text('dict')`` into per-line text blocks and sizes.

    Image blocks (``type == 1``) are skipped. Unknown dict shapes return
    empty so the adapter can fall back to ``get_text('blocks')``. Lines are
    emitted separately so a large title is not absorbed into body copy.

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
            for span in spans:
                if not isinstance(span, dict):
                    continue
                span_map = cast(dict[object, object], span)
                text = str(span_map.get("text") or "")
                if text:
                    line_parts.append(text)
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
            cleaned = "".join(line_parts).strip()
            if not cleaned:
                continue
            bbox = _pdf_block_bbox(line_map.get("bbox")) or block_bbox
            collected.append(
                PdfTextBlock(
                    text=cleaned,
                    bbox=bbox,
                    max_size=max_size,
                    bold=bold,
                    block_index=block_index,
                )
            )
    return tuple(collected), tuple(sizes)


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
