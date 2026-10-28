"""Fit a contiguous, query-relevant window without changing canonical evidence."""

from __future__ import annotations

import re
from collections import Counter

_WORD = re.compile(r"[\w]+", re.UNICODE)
_STOP = frozenset(
    "a an and are as at be by can cite does for from how in is it of on or "
    "source the their this to use using what when which with according official".split()
)


def query_excerpt_window(text: str, query: str, size: int) -> str:
    """Select an exact contiguous window, favoring repeated query anchors.

    No source text is generated or joined across gaps. Ties preserve the earliest
    window, and queries without useful anchors retain prefix behavior.
    """
    if len(text) <= size:
        return text
    terms = {
        word.casefold()
        for word in _WORD.findall(query)
        if (len(word) >= 3 or word.isdecimal()) and word.casefold() not in _STOP
    }
    if not terms:
        return text[:size]
    step = max(1, size // 4)
    starts = (*range(0, len(text) - size + 1, step), len(text) - size)

    def score(start: int) -> int:
        """Count bounded exact-token overlap, emphasizing numeric identifiers."""
        words = Counter(_WORD.findall(text[start : start + size].casefold()))
        return sum(
            min(words[term], 4) * (2 if term.isdecimal() else 1) for term in terms
        )

    start = max(starts, key=score)
    return text[start : start + size]
