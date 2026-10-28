"""Detect missing requested conformance metadata without inventing its value."""

from __future__ import annotations

import re

_REFERENCE = re.compile(r"\b\d+(?:\.\d+){2,}\b")
_LEVEL = re.compile(r"\bLevel\s+[A-Za-z0-9-]+\b|\(\s*A{1,3}\s*\)", re.I)


def missing_level_references(query: str, texts: tuple[str, ...]) -> frozenset[str]:
    """Find requested numbered criteria lacking nearby explicit level evidence.

    This controls a bounded read of an existing candidate, never an answer or
    inferred conformance value. Another numbered reference ends the window so
    a neighbouring criterion's level cannot establish coverage.
    """
    if not re.search(r"\bconformance\s+levels?\b", query, re.I):
        return frozenset()
    requested = set(_REFERENCE.findall(query))
    covered: set[str] = set()
    for text in texts:
        for match in _REFERENCE.finditer(text):
            reference = match.group()
            if reference not in requested:
                continue
            tail = text[match.end() : match.end() + 180]
            next_reference = _REFERENCE.search(tail)
            if next_reference is not None:
                tail = tail[: next_reference.start()]
            if _LEVEL.search(tail):
                covered.add(reference)
    return frozenset(requested - covered)


def title_mentions_reference(title: str, references: frozenset[str]) -> bool:
    """Select only a candidate explicitly titled for the missing criterion."""
    return bool(set(_REFERENCE.findall(title)) & references)
