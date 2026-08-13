"""Versioned PDF repeated header/footer cleaning."""

from __future__ import annotations

from collections import Counter

from smart_rag_core.ingestion.parser.types import RemovalDiagnostic


def detect_repeated_lines(
    page_lines: list[list[str]],
    *,
    min_pages: int = 2,
    min_occurrence_ratio: float = 0.6,
) -> set[str]:
    """Detect lines repeated across pages as header/footer candidates.

    Args:
        page_lines: Per-page non-empty stripped lines.
        min_pages: Minimum pages required before removal.
        min_occurrence_ratio: Fraction of pages line must appear on.

    Returns:
        Set of normalized line texts to remove.
    """

    if len(page_lines) < min_pages:
        return set()
    counts: Counter[str] = Counter()
    for lines in page_lines:
        for line in {line.strip() for line in lines if line.strip()}:
            counts[line] += 1
    threshold = max(2, int(len(page_lines) * min_occurrence_ratio))
    return {line for line, count in counts.items() if count >= threshold}


def remove_repeated_lines(
    page_lines: list[list[str]],
    repeated: set[str],
) -> tuple[list[list[str]], tuple[RemovalDiagnostic, ...]]:
    """Remove repeated header/footer lines and emit diagnostics.

    Args:
        page_lines: Original per-page lines.
        repeated: Lines to strip when matched exactly.

    Returns:
        Cleaned page lines and removal diagnostics.
    """

    cleaned: list[list[str]] = []
    removals: list[RemovalDiagnostic] = []
    for _page_index, lines in enumerate(page_lines):
        kept: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and stripped in repeated:
                removals.append(
                    RemovalDiagnostic(
                        reason="repeated_header_footer",
                        text_preview=stripped[:120],
                        locator=None,
                        occurrences=1,
                    )
                )
                continue
            kept.append(line)
        cleaned.append(kept)
    return cleaned, tuple(removals)
