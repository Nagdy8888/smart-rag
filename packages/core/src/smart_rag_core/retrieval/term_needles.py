"""Bounded ranking-query needles for the Hybrid term channel."""

from __future__ import annotations

import re
from collections.abc import Sequence

from smart_rag_core.query_profile.aliases import resolve_approved_aliases
from smart_rag_core.query_profile.extract import extract_codes
from smart_rag_core.retrieval.profiles import (
    MAX_NORMALIZED_QUERY_CHARS,
    TERM_EXTRA_NEEDLE_CAP,
)
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

_IDENTIFIER = re.compile(
    r"\b[A-Z]{2,10}(?:[-_/#][A-Z0-9]{2,24})+\b",
)
_ACRONYM = re.compile(r"\b[A-Z]{3,8}\b")
_CAMEL = re.compile(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9]{1,40}\b")
_ENTITY = re.compile(
    r"\b(?:[A-Z][a-z]{2,24})(?:\s+[A-Z][a-z]{2,24}){1,3}\b",
)
_QUOTES = re.compile(r'"([^"]{1,200})"')
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_COMMON_ACRONYMS = frozenset(
    {
        "THE",
        "AND",
        "FOR",
        "ARE",
        "BUT",
        "NOT",
        "YOU",
        "ALL",
        "CAN",
        "HAS",
        "WAS",
        "HIS",
        "HER",
        "ITS",
        "OUR",
        "ANY",
        "WHO",
        "HOW",
        "WHY",
        "WHAT",
        "WHEN",
        "THAT",
        "THIS",
        "WITH",
        "FROM",
        "YOUR",
        "HAVE",
        "BEEN",
        "WILL",
        "THEY",
        "THEM",
        "THEN",
        "THAN",
        "ALSO",
        "JUST",
        "INTO",
        "OVER",
        "ONLY",
        "SOME",
        "SUCH",
        "EACH",
        "BOTH",
        "MOST",
        "VERY",
        "MORE",
        "LESS",
        "MANY",
        "MUCH",
        "LIKE",
    }
)


def extract_term_needles(
    query: str,
    *,
    extra: Sequence[str] = (),
) -> tuple[str, ...]:
    """Extract bounded codes, acronyms, entities, and aliases from a query.

    The remaining sentence is still retrieved separately. Needles are additive
    exact/trigram targets so a long question can still hit a short indexed
    term. SQL metacharacters stay data, never concatenated into SQL.

    Args:
        query: Ranking query after source-selector stripping.
        extra: Optional profile entities or approved aliases already in the
            query. Values that do not appear in the query are ignored so
            unauthorized glossary rows cannot be injected client-side.

    Returns:
        At most eight distinct normalized needles, excluding the full sentence
        when it is longer than a single token.
    """

    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        """Keep one bounded normalized needle.

        Args:
            raw: Candidate token or phrase.
        """

        if "\x00" in raw:
            return
        normalized = normalize_arabic_v1(raw).strip()[:MAX_NORMALIZED_QUERY_CHARS]
        if len(normalized) < 2 or normalized.casefold() in seen:
            return
        seen.add(normalized.casefold())
        found.append(normalized)

    for code in extract_codes(query):
        _add(code)
    for match in _IDENTIFIER.finditer(query):
        _add(match.group(0))
    for match in _ACRONYM.finditer(query):
        token = match.group(0)
        if token not in _COMMON_ACRONYMS:
            _add(token)
    for match in _CAMEL.finditer(query):
        _add(match.group(0))
    for match in _ENTITY.finditer(query):
        _add(match.group(0))
    for match in _QUOTES.finditer(query):
        _add(match.group(1))
    for alias in resolve_approved_aliases(query):
        _add(alias)
    haystack = normalize_arabic_v1(query)
    for item in extra:
        candidate = item.strip()
        if candidate and candidate.casefold() in haystack.casefold():
            _add(candidate)
    for token in haystack.split():
        if _ARABIC.search(token) and len(token) >= 3:
            _add(token)
    sentence = normalize_arabic_v1(query).strip()
    return tuple(
        item
        for item in found[:TERM_EXTRA_NEEDLE_CAP]
        if item.casefold() != sentence.casefold()
    )


def expand_term_texts(texts: Sequence[str]) -> tuple[str, ...]:
    """Keep ranking texts and append needles from the first ranking query.

    Args:
        texts: Original ranking query plus at most three variants.

    Returns:
        Ranking texts followed by distinct extra needles.
    """

    ordered: list[str] = []
    seen: set[str] = set()
    for text in texts:
        stripped = text.strip()
        if not stripped or stripped.casefold() in seen:
            continue
        seen.add(stripped.casefold())
        ordered.append(text)
    primary = texts[0] if texts else ""
    for needle in extract_term_needles(primary):
        if needle.casefold() in seen:
            continue
        seen.add(needle.casefold())
        ordered.append(needle)
    return tuple(ordered)
