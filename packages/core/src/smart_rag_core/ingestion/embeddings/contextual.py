"""Contextual embedding input construction without mutating citation text."""

from __future__ import annotations

import re
from uuid import UUID

from smart_rag_core.ingestion.chunking.types import CanonicalChunk

_CODE_PATTERN = re.compile(
    r"\b(?:PO|INV|TKT|REF|SKU|SN|ID)[-_#: ]?[A-Z0-9]{3,32}\b",
    re.IGNORECASE,
)


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
    """Populate search terms from title, headings, filename, and code patterns.

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
        for match in _CODE_PATTERN.findall(chunk.raw_text):
            terms.add(match.strip())
        result[chunk.chunk_id] = tuple(sorted(terms))
    return result
