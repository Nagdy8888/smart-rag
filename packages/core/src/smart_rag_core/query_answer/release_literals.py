"""Split from ``release.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.format_shape import (
    strip_markdown_fences_for_literal_guard,
)
from smart_rag_core.query_answer.models import (
    AtomicLink,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.models import TableEvidenceRecord

_ACRONYM_PAREN = re.compile(r"\b([A-Z]{2,10})\s*\(([^)]{2,80})\)")

_PAREN_ACRONYM = re.compile(
    r"\b([A-Z][A-Za-z0-9][A-Za-z0-9 ./-]{1,60}?)\s*\(([A-Z]{2,10})\)"
)

_STANDS_FOR = re.compile(
    r"\b([A-Z]{2,10})\s+(?:stands for|means|is short for|expands to)\s+"
    r"([A-Za-z][A-Za-z0-9 ./-]{1,80})",
    re.IGNORECASE,
)

_TITLE_PHRASE = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)+)\b")

_QUOTED = re.compile(r"\"([^\"]{1,200})\"|'([^']{1,200})'|`([^`]{1,200})`")

_TRAILING_QUOTE_PUNCTUATION = ".,;:!?…"

_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")

_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

_NAMED_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)

_CODE_TOKEN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*(?:\(\))?")


def fact_literals_missing(claim: str, source_text: str) -> bool:
    """Return whether a fact claim uses literals absent from the cited source.

    Args:
        claim: Fact-link claim.
        source_text: Cited canonical text.

    Returns:
        True when a required quoted, numeric, date, or code literal is
        absent. A trailing sentence mark inside a quote is not a new
        literal when the quoted words themselves occur in the source.
    """

    for match in _QUOTED.finditer(claim):
        literal = next(item for item in match.groups() if item)
        if not _quoted_literal_in_source(literal, source_text):
            return True
    for match in _NUMBER.finditer(claim):
        if match.group(0) not in source_text:
            return True
    for pattern in (_ISO_DATE, _NAMED_DATE, _CODE_TOKEN):
        for match in pattern.finditer(claim):
            if match.group(0) not in source_text:
                return True
    return False


def acronym_expansion_fails(claim: str, source_text: str) -> bool:
    """Return whether the claim invents or mismatches an acronym expansion.

    Args:
        claim: Atomic claim or paragraph sentence.
        source_text: Cited canonical text.

    Returns:
        True when an expansion is not spelled in the source or conflicts.
    """

    source_defs = _acronym_expansions(source_text)
    claim_defs = _acronym_expansions(claim)
    normalized_source = release_normalize_text(source_text)
    for acronym, expansions in claim_defs.items():
        allowed = set(source_defs.get(acronym, set()))
        for expansion in expansions:
            if expansion and expansion in normalized_source:
                allowed.add(expansion)
        if not allowed or any(item not in allowed for item in expansions):
            return True
    claim_phrases = _title_phrases(claim)
    for expansions in source_defs.values():
        for expansion in expansions:
            words = expansion.split()
            if len(words) < 2:
                continue
            last = words[-1]
            for phrase in claim_phrases:
                phrase_words = phrase.split()
                if (
                    len(phrase_words) == len(words)
                    and phrase_words[-1] == last
                    and phrase not in expansions
                ):
                    return True
    return False


def link_fails_literal_guard(
    link: AtomicLink,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> bool:
    """Return whether one link invents an expansion or missing fact literal.

    Args:
        link: Candidate atomic claim.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        True when the claim must be dropped.
    """

    source_text = cited_source_text(link, fusion=fusion, tables=tables)
    claim_for_guard = strip_markdown_fences_for_literal_guard(link.claim)
    if acronym_expansion_fails(claim_for_guard, source_text):
        return True
    if link.kind != "fact":
        return False
    return fact_literals_missing(claim_for_guard, source_text)


def cited_source_text(
    link: AtomicLink,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> str:
    """Join cited passage and table text for one link.

    Args:
        link: Atomic claim.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        Concatenated cited source text.
    """

    passages = {item.chunk_id: item.citation_text for item in fusion.evidence}
    bodies = [passages[chunk_id] for chunk_id in link.chunk_ids if chunk_id in passages]
    if link.table_id:
        record = next((item for item in tables if item.table_id == link.table_id), None)
        if record is not None:
            bodies.append(f"{record.operation} {record.rows} {record.source_ranges}")
    return "\n".join(bodies)


def release_normalize_text(text: str) -> str:
    """Collapse case and whitespace for exact expansion compares.

    Args:
        text: Raw expansion or phrase.

    Returns:
        Lowercased collapsed form.
    """

    return " ".join(text.strip().lower().split()).strip(".,:;!?")


def _title_phrases(text: str) -> tuple[str, ...]:
    """Return Title Case multi-word phrases.

    Args:
        text: Source or claim text.

    Returns:
        Normalized phrases with at least two words.
    """

    return tuple(
        release_normalize_text(item.group(0)) for item in _TITLE_PHRASE.finditer(text)
    )


def _acronym_expansions(text: str) -> dict[str, set[str]]:
    """Extract acronym-to-expansion maps from definition-shaped phrases.

    Args:
        text: Source or claim text.

    Returns:
        Acronym keys mapped to normalized expansions.
    """

    found: dict[str, set[str]] = {}
    for match in _ACRONYM_PAREN.finditer(text):
        found.setdefault(match.group(1), set()).add(
            release_normalize_text(match.group(2))
        )
    for match in _PAREN_ACRONYM.finditer(text):
        found.setdefault(match.group(2), set()).add(
            release_normalize_text(match.group(1))
        )
    for match in _STANDS_FOR.finditer(text):
        found.setdefault(match.group(1).upper(), set()).add(
            release_normalize_text(match.group(2))
        )
    return found


def source_occurrence(needle: str, source: str) -> str | None:
    """Return the passage's own spelling of ``needle``.

    Args:
        needle: Text taken from a claim.
        source: Cited canonical passage or table text.

    Returns:
        The matching substring copied from ``source``, or ``None`` when
        those words are absent. Capitalization may differ.
    """

    if not needle:
        return None
    match = re.search(re.escape(needle), source, re.IGNORECASE)
    if match is None:
        return None
    return match.group(0)


def _quoted_literal_in_source(literal: str, source_text: str) -> bool:
    """Return whether quoted words occur verbatim in the cited source.

    The comparison does not rewrite the claim and does not invent a
    quote. A trailing sentence mark is ignored only when the remaining
    text is non-empty and already present in ``source_text``. Letter
    case is not a mismatch: ``higher`` matches ``Higher``.

    Args:
        literal: Text inside one pair of quotes or backticks.
        source_text: Cited canonical passage or table text.

    Returns:
        True when ``literal``, or ``literal`` without trailing sentence
        punctuation, occurs in ``source_text`` ignoring capitalization.
    """

    if source_occurrence(literal, source_text) is not None:
        return True
    stripped = literal.rstrip(_TRAILING_QUOTE_PUNCTUATION)
    if not stripped or stripped == literal:
        return False
    return source_occurrence(stripped, source_text) is not None
