"""Contextual embedding input construction without mutating citation text."""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from smart_rag_core.ingestion.chunking.types import CanonicalChunk
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

_CODE_PATTERNS = (
    re.compile(
        r"\b(?:PO|INV|TKT|REF|SKU|SN|ID)[-_#: ]?[A-Z0-9]{3,32}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bINV-SR-\d{4}\b"),
    re.compile(r"\bSKU-P4-[A-Z0-9]{3}\b"),
    re.compile(r"\bPRJ-[A-Z]{5,12}\b"),
    re.compile(r"\bP4-[A-Z]{2}-\d{3}\b"),
)
_ACRONYM_PAREN = re.compile(r"\b([A-Z]{2,8})\s+\(([^)]{3,80})\)")
_DEF_PAREN_ACRONYM = re.compile(
    r"\b((?:[A-Z][A-Za-z]+(?:[-][A-Z]?[A-Za-z]+)*)"
    r"(?:\s+[A-Z][A-Za-z]+(?:[-][A-Z]?[A-Za-z]+)*){1,6})\s+\(([A-Z]{2,8})\)"
)
_CAMEL_TOKEN = re.compile(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9]{1,40}\b")


def build_contextual_embedding_text(
    *,
    document_title: str,
    chunk: CanonicalChunk,
) -> str:
    """Build title + heading path + passage text for embedding only.

    Args:
        document_title: Canonical document title.
        chunk: One passage chunk with heading ancestry.

    Returns:
        Deterministic contextual string; ``chunk.raw_text`` remains citation text.
    """

    heading_path = " > ".join(chunk.section_path) if chunk.section_path else ""
    parts = [document_title.strip()]
    if heading_path:
        parts.append(heading_path)
    parts.append(chunk.raw_text.strip())
    return "\n".join(part for part in parts if part)


def extract_deterministic_search_terms(
    *,
    document_title: str,
    filename: str | None,
    chunks: tuple[CanonicalChunk, ...],
) -> dict[UUID, tuple[str, ...]]:
    """Populate search terms from titles, headings, codes, and acronyms.

    Phase 4 identifier rules INV-SR-####, SKU-P4-xxx, PRJ- names, and P4-xx-###
    are included alongside the original PO/INV/TKT/REF/SKU/SN/ID extractor.
    Parenthetical acronyms and mixed-case tokens are added only as generic
    parse-gap terms.

    Args:
        document_title: Document title.
        filename: Original filename when available.
        chunks: Representative passage chunks only.

    Returns:
        Mapping of chunk ID to deduplicated normalized term strings.
    """

    shared: set[str] = set()
    if document_title.strip():
        shared.add(document_title.strip())
    if filename:
        stem = filename.rsplit(".", maxsplit=1)[0]
        if stem.strip():
            shared.add(stem.strip())

    result: dict[UUID, tuple[str, ...]] = {}
    for chunk in chunks:
        if not chunk.is_search_representative:
            continue
        terms: set[str] = set(shared)
        for heading in chunk.section_path:
            if heading.strip():
                terms.add(heading.strip())
        for pattern in _CODE_PATTERNS:
            for match in pattern.findall(chunk.raw_text):
                terms.add(match.strip())
        terms.update(_acronym_and_mixed_case_terms(chunk.raw_text))
        result[chunk.chunk_id] = tuple(sorted(terms))
    return result


def needle_in_index_gaps(
    needles: Sequence[str],
    indexed_terms: Sequence[str],
) -> tuple[str, ...]:
    """Return needles that are absent from an indexed term list.

    Args:
        needles: Query or audit tokens.
        indexed_terms: Terms already stored for a chunk or version.

    Returns:
        Needles whose normalized form is missing from the index.
    """

    indexed = {
        normalize_arabic_v1(item).casefold() for item in indexed_terms if item.strip()
    }
    missing: list[str] = []
    seen: set[str] = set()
    for needle in needles:
        key = normalize_arabic_v1(needle).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        if key not in indexed:
            missing.append(needle)
    return tuple(missing)


def _acronym_and_mixed_case_terms(text: str) -> set[str]:
    """Extract parenthetical acronyms and mixed-case tokens.

    Args:
        text: Canonical citation text. Never mutated.

    Returns:
        Extra search terms proven useful when a needle-in-index audit misses
        the acronym or mixed-case form.
    """

    terms: set[str] = set()
    for match in _ACRONYM_PAREN.finditer(text):
        terms.add(match.group(1).strip())
        terms.add(match.group(2).strip())
    for match in _DEF_PAREN_ACRONYM.finditer(text):
        terms.add(match.group(1).strip())
        terms.add(match.group(2).strip())
    for match in _CAMEL_TOKEN.finditer(text):
        terms.add(match.group(0).strip())
    return {item for item in terms if item}
