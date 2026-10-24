"""Conservative exact evidence matching on a single authorized PDF page."""

from __future__ import annotations

import re
import unicodedata
from typing import Protocol, cast

import fitz


class HighlightAnnotation(Protocol):
    """Small typed boundary for PyMuPDF annotations."""

    def set_opacity(self, opacity: float) -> None:
        """Set translucent highlight opacity."""
        ...

    def update(self) -> None:
        """Apply the annotation appearance."""
        ...


class HighlightPage(Protocol):
    """Read page words and apply transient preview annotations."""

    def get_text(self, option: str) -> object:
        """Return native text words with page coordinates."""
        ...

    def add_highlight_annot(self, quads: list[fitz.Rect]) -> HighlightAnnotation:
        """Add an annotation only to this in-memory document."""
        ...


class _RectGeometry(Protocol):
    """Typed numeric geometry boundary for vendor rectangle properties."""

    x0: float
    x1: float
    height: float


def _canonical(text: str) -> str:
    """Normalize layout, ligatures and punctuation without substituting words."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", text).casefold()
        if character.isalnum()
    )


def _unique_span(source: str, target: str) -> range | None:
    """Accept just one occurrence, including overlapping duplicates."""
    start = source.find(target)
    if start < 0 or source.find(target, start + 1) >= 0:
        return None
    return range(start, start + len(target))


def _matched_positions(source: str, excerpt: str) -> set[int]:
    """Locate a whole passage, or independently exact table rows/cells and sentences."""
    target = _canonical(excerpt)
    if len(target) < 24:
        return set()
    whole = _unique_span(source, target)
    if whole is not None:
        return set(whole)
    selected: set[int] = set()
    cells: list[range] = []
    for fragment in re.split(r"\n+|(?<=[.!?;])\s+", excerpt):
        normalized = _canonical(fragment)
        minimum = 24 if "|" in fragment else 48
        if len(normalized) >= minimum:
            span = _unique_span(source, normalized)
            if span is not None:
                selected.update(span)
        if "|" in fragment:
            for cell in fragment.split("|"):
                normalized_cell = _canonical(cell)
                if len(normalized_cell) < 6:
                    continue
                span = _unique_span(source, normalized_cell)
                if span is not None:
                    cells.append(span)
    # A lone common cell cannot establish that the table was located.
    if len({(cell.start, cell.stop) for cell in cells}) >= 2:
        for cell in cells:
            selected.update(cell)
    return selected


def highlight_cited_passage(page: HighlightPage, excerpt: str) -> bool:
    """Highlight exact cited text despite PDF wrapping or Markdown table layout.

    Args:
        page: The already authorized physical PDF page.
        excerpt: Server-stored citation evidence, never browser-supplied text.

    Returns:
        Whether any sufficiently specific, unique evidence was located.
        Unmatched or ambiguous text is never guessed. Only actual matched
        fragments are marked when an excerpt includes synthetic table headers
        or material not present on this physical page.
    """
    if not excerpt or len(excerpt) > 8000:
        return False
    raw_words = page.get_text("words")
    if not isinstance(raw_words, list):
        return False
    words = cast(list[object], raw_words)
    if len(words) > 20000:
        return False
    characters: list[str] = []
    positions: list[int] = []
    geometry: list[tuple[fitz.Rect, tuple[int, int]]] = []
    for raw_word in words:
        if not isinstance(raw_word, (list, tuple)):
            continue
        word = cast(list[object] | tuple[object, ...], raw_word)
        if len(word) < 8 or not isinstance(word[4], str):
            continue
        if not all(isinstance(value, (int, float)) for value in word[:4]):
            continue
        if not isinstance(word[5], int) or not isinstance(word[6], int):
            continue
        rect = fitz.Rect(*(cast(float, value) for value in word[:4]))
        if len(word[4]) > 20000:
            return False
        normalized = _canonical(word[4])
        if len(positions) + len(normalized) > 200000:
            return False
        positions.extend([len(geometry)] * len(normalized))
        characters.append(normalized)
        geometry.append((rect, (word[5], word[6])))
    matched = _matched_positions("".join(characters), excerpt)
    if not matched:
        return False
    lines: dict[tuple[int, int], list[fitz.Rect]] = {}
    for index in sorted({positions[position] for position in matched}):
        rect, line = geometry[index]
        lines.setdefault(line, []).append(rect)
    rectangles: list[fitz.Rect] = []
    for line_rects in lines.values():
        merged: fitz.Rect | None = None
        for rect in sorted(line_rects, key=lambda item: cast(_RectGeometry, item).x0):
            # Do not paint across an uncited column or a gap in selected words.
            if merged is not None and cast(_RectGeometry, rect).x0 - cast(
                _RectGeometry, merged
            ).x1 <= max(4, cast(_RectGeometry, rect).height * 0.8):
                merged |= rect
            else:
                if merged is not None:
                    rectangles.append(merged)
                merged = fitz.Rect(rect)
        if merged is not None:
            rectangles.append(merged)
    if len(rectangles) > 500:
        return False
    annotation = page.add_highlight_annot(rectangles)
    annotation.set_opacity(0.35)
    annotation.update()
    return True
