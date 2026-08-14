"""Unit tests for Packet 2 retrieval profiles, BM25 constructors, and terms."""

from __future__ import annotations

from uuid import uuid4

import pytest
from smart_rag_core.ingestion.chunking.types import (
    CanonicalChunk,
    ChunkKind,
    ChunkProvenance,
)
from smart_rag_core.ingestion.embeddings.contextual import (
    extract_deterministic_search_terms,
)
from smart_rag_core.retrieval.bm25_query import Bm25QueryError, build_bm25_query
from smart_rag_core.retrieval.profiles import (
    EXACT_FALLBACK_AUTHORIZED_ROW_CAP,
    Bm25Field,
    Bm25Operator,
    DenseMode,
    admit_exact_fallback,
    resolve_hnsw_profile,
)


def _passage(text: str) -> CanonicalChunk:
    """Return one passage chunk for term extraction tests.

    Args:
        text: Raw citation text.

    Returns:
        Canonical passage chunk.
    """

    return CanonicalChunk(
        chunk_id=uuid4(),
        chunk_index=0,
        kind=ChunkKind.PASSAGE,
        raw_text=text,
        token_count=12,
        provenance=ChunkProvenance(
            parser_version="parser_v1",
            cleaning_version="cleaning_v1",
            chunking_version="chunking_v1",
            tokenizer_version="cl100k_base_v1",
            dedup_policy_version="dedup_v1",
            normalized_content_hash="abc123",
        ),
    )


def test_unknown_hnsw_profile_fails_closed() -> None:
    """Unlisted HNSW profile names are rejected."""

    with pytest.raises(ValueError, match="unknown_retrieval_profile"):
        resolve_hnsw_profile("unlimited")


def test_exact_fallback_admission_uses_hard_row_cap() -> None:
    """Exact fallback is refused above 10,000 authorized rows."""

    assert admit_exact_fallback(EXACT_FALLBACK_AUTHORIZED_ROW_CAP) is DenseMode.EXACT
    assert (
        admit_exact_fallback(EXACT_FALLBACK_AUTHORIZED_ROW_CAP + 1)
        is DenseMode.WEAK_EVIDENCE
    )


def test_bm25_query_rejects_empty_and_unknown_field() -> None:
    """Empty normalized queries and unknown fields fail closed."""

    with pytest.raises(Bm25QueryError, match="empty_bm25_query"):
        build_bm25_query(
            query_text="   ",
            operator=Bm25Operator.MATCH_DISJUNCTION,
            field=Bm25Field.BODY,
        )
    with pytest.raises(ValueError):
        Bm25Field("pdb.parse")


def test_bm25_query_normalizes_but_does_not_parse_operators() -> None:
    """Injection-like query text is normalized as literals, not parsed."""

    query = build_bm25_query(
        query_text="leave ||| ### pdb.parse('x')",
        operator=Bm25Operator.MATCH_DISJUNCTION,
        field=Bm25Field.BODY,
    )
    assert "|||" not in query.field.value
    assert query.operator is Bm25Operator.MATCH_DISJUNCTION
    assert "pdb.parse" in query.query_normalized or "pdb" in query.query_normalized


def test_phase4_identifier_patterns_populate_terms() -> None:
    """INV-SR, SKU-P4, and PRJ codes are extracted into the term channel."""

    chunk = _passage("See INV-SR-8801 and SKU-P4-AA1 for PRJ-ORIONALPHA")
    terms = extract_deterministic_search_terms(
        document_title="Visible Policy",
        filename="policy.pdf",
        chunks=(chunk,),
    )
    extracted = set(terms[chunk.chunk_id])
    assert "INV-SR-8801" in extracted
    assert "SKU-P4-AA1" in extracted
    assert "PRJ-ORIONALPHA" in extracted
    assert "Visible Policy" in extracted
    assert "policy" in extracted
