"""Unit tests for generic search-term enrichment and needle-in-index gaps."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.ingestion.chunking.types import (
    CanonicalChunk,
    ChunkKind,
    ChunkProvenance,
)
from smart_rag_core.ingestion.embeddings.contextual import (
    extract_deterministic_search_terms,
    needle_in_index_gaps,
)


def _passage(text: str) -> CanonicalChunk:
    """Return one passage chunk.

    Args:
        text: Canonical citation text.

    Returns:
        Search-representative passage.
    """

    return CanonicalChunk(
        chunk_id=uuid4(),
        chunk_index=0,
        kind=ChunkKind.PASSAGE,
        raw_text=text,
        token_count=16,
        provenance=ChunkProvenance(
            parser_version="parser_v1",
            cleaning_version="cleaning_v1",
            chunking_version="chunking_v1",
            tokenizer_version="cl100k_base_v1",
            dedup_policy_version="dedup_v1",
            normalized_content_hash="abc123",
        ),
    )


def test_acronym_and_mixed_case_fill_index_gaps() -> None:
    """Parenthetical acronyms and CamelCase tokens become searchable terms."""

    chunk = _passage(
        "Hypertext Transfer Protocol (HTTP) is defined beside OpenAPI."
    )
    title_only = ("Policy Handbook",)
    gaps = needle_in_index_gaps(("HTTP", "OpenAPI"), title_only)
    assert gaps == ("HTTP", "OpenAPI")
    indexed = extract_deterministic_search_terms(
        document_title="Policy Handbook",
        filename="policy.pdf",
        chunks=(chunk,),
    )
    terms = indexed[chunk.chunk_id]
    remaining = needle_in_index_gaps(("HTTP", "OpenAPI"), terms)
    assert remaining == ()
    assert "HTTP" in terms
    assert "OpenAPI" in terms
    assert "Hypertext Transfer Protocol" in terms


def test_enrichment_does_not_add_injected_gold_phrases() -> None:
    """Needles that never appear in the chunk stay out of the index."""

    chunk = _passage("HTTP (Hypertext Transfer Protocol) uses OpenAPI.")
    terms = extract_deterministic_search_terms(
        document_title="Policy Handbook",
        filename="policy.pdf",
        chunks=(chunk,),
    )[chunk.chunk_id]
    assert "benchmark-gold-phrase" not in terms
    assert needle_in_index_gaps(("benchmark-gold-phrase",), terms) == (
        "benchmark-gold-phrase",
    )
