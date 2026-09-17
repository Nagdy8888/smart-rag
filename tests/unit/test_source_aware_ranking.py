"""Metamorphic tests for source-aware ranking and post-ACL duplicate collapse."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.retrieval.context import passages_from_context
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.rerank import (
    RerankPassage,
    build_rerank_pool,
    collapse_exact_duplicate_passages,
)
from smart_rag_core.retrieval.source_scope import strip_source_selectors
from smart_rag_core.retrieval.types import RetrievalCandidate


def _candidate(document=None, chunk=None) -> RetrievalCandidate:
    """Build one fused candidate.

    Args:
        document: Optional document id.
        chunk: Optional chunk id.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=chunk or uuid4(),
        document_id=document or uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def _passage(*, text: str, document=None, chunk=None) -> RerankPassage:
    """Build one authorized rerank passage.

    Args:
        text: Canonical citation text.
        document: Optional document id.
        chunk: Optional chunk id.

    Returns:
        Passage used by pool construction.
    """

    candidate = _candidate(document=document, chunk=chunk)
    return RerankPassage(
        candidate=candidate,
        raw_text=text,
        section_path=(),
        page_number=1,
        parent_chunk_id=None,
        chunk_index=0,
        token_count=len(text.split()),
        channels=frozenset({"dense"}),
        excerpt=text,
    )


def test_adding_document_title_does_not_distort_ranking_query() -> None:
    """Equivalent questions with or without a title share ranking tokens."""

    fact_query = "What is INV-1001?"
    titled = "In Policy Handbook, what is INV-1001?"
    stripped = strip_source_selectors(titled, ("Policy Handbook",))
    assert "INV-1001" in stripped
    assert "INV-1001" in fact_query
    assert "Policy Handbook" not in stripped


def test_exact_duplicate_copies_do_not_evict_supporting_passage() -> None:
    """Later exact copies collapse after ACL text is present."""

    support = "The listed code is INV-1001."
    first = _passage(text=support)
    duplicate = _passage(text=support)
    other = _passage(text="A distinct later heading remains available.")
    collapsed = collapse_exact_duplicate_passages((first, duplicate, other))
    assert len(collapsed) == 2
    assert collapsed[0].candidate.chunk_id == first.candidate.chunk_id
    assert collapsed[1].candidate.chunk_id == other.candidate.chunk_id
    pool = build_rerank_pool((first, duplicate, other), pool_size=8, max_per_document=2)
    ids = {item.candidate.chunk_id for item in pool}
    assert first.candidate.chunk_id in ids
    assert duplicate.candidate.chunk_id not in ids
    assert other.candidate.chunk_id in ids


def test_unauthorized_context_never_enters_the_pool() -> None:
    """Chunks missing from ACL-rechecked context cannot occupy ranking slots."""

    allowed = uuid4()
    denied = uuid4()
    fused = (
        _candidate(chunk=allowed),
        _candidate(chunk=denied),
    )
    context = (
        ChunkContext(
            chunk_id=allowed,
            document_id=uuid4(),
            version_id=uuid4(),
            parent_chunk_id=None,
            chunk_index=0,
            page_number=1,
            section_path=(),
            token_count=4,
            raw_text="The listed code is INV-1001.",
            is_search_representative=True,
        ),
    )
    passages = passages_from_context(
        fused,
        context,
        {allowed: frozenset({"dense"}), denied: frozenset({"dense"})},
    )
    assert [item.candidate.chunk_id for item in passages] == [allowed]
    pool = build_rerank_pool(passages, pool_size=8)
    assert [item.candidate.chunk_id for item in pool] == [allowed]
