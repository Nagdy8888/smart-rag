"""Explicit page cites drive page-scoped Hybrid recall helpers."""

from __future__ import annotations

from uuid import UUID, uuid4

from smart_rag_core.retrieval.rerank import (
    CHANNEL_HEAD_PIN,
    RerankPassage,
    merge_rerank_pins,
    named_page_numbers,
    page_head_pins,
    promote_named_page_passages,
)
from smart_rag_core.retrieval.types import RetrievalCandidate


def _passage(*, page: int | None, text: str = "body") -> RerankPassage:
    """Build a minimal passage for promotion tests.

    Args:
        page: Optional page number on the passage.
        text: Passage body.

    Returns:
        RerankPassage with a fresh chunk id.
    """

    chunk_id = uuid4()
    return RerankPassage(
        candidate=RetrievalCandidate(
            chunk_id=chunk_id,
            document_id=uuid4(),
            version_id=uuid4(),
            channel_rank=1,
            channel_score=1.0,
        ),
        raw_text=text,
        page_number=page,
        token_count=max(1, len(text.split())),
        channels=frozenset({"term"}),
        excerpt=text,
    )


def test_named_page_numbers_extracts_single_and_range() -> None:
    """Numeric page cites parse; bare ``this page`` does not."""

    assert named_page_numbers("Quote the claim on page 27.") == (27,)
    assert named_page_numbers("See pages 10-12 for the table.") == (10, 11, 12)
    assert named_page_numbers("main claim on this page") == ()
    assert named_page_numbers("Use page 26.") == (26,)


def test_promote_named_page_pins_matching_passage() -> None:
    """A cited page passage is pinned first when present in the pool."""

    other = _passage(page=1, text="other")
    target = _passage(page=27, text="target")
    trimmed = (other,)
    promoted = promote_named_page_passages(
        trimmed,
        query="Quote the wording on page 27.",
        pool=(other, target),
        limit=2,
    )
    assert promoted[0].page_number == 27
    assert promoted[0].raw_text == "target"


def test_page_head_pins_keeps_matching_fused_ids() -> None:
    """Cited-page fused IDs are reserved; non-matching pages are skipped."""

    match_a = uuid4()
    other = uuid4()
    match_b = uuid4()
    fused = (other, match_a, match_b)
    page_by_id: dict[UUID, int | None] = {
        other: 1,
        match_a: 27,
        match_b: 27,
    }
    pins = page_head_pins(
        fused_ids=fused,
        page_by_id=page_by_id,
        pages=(27,),
        head=CHANNEL_HEAD_PIN,
    )
    assert pins == (match_a, match_b)


def test_page_head_pins_empty_without_cite_or_when_capped() -> None:
    """No cite yields no pins; head caps the reserved set."""

    first = uuid4()
    second = uuid4()
    third = uuid4()
    fused = (first, second, third)
    page_by_id = {first: 9, second: 9, third: 9}
    assert (
        page_head_pins(
            fused_ids=fused,
            page_by_id=page_by_id,
            pages=(),
            head=2,
        )
        == ()
    )
    capped = page_head_pins(
        fused_ids=fused,
        page_by_id=page_by_id,
        pages=(9,),
        head=2,
    )
    assert capped == (first, second)


def test_merge_rerank_pins_puts_page_pins_first() -> None:
    """Page pins precede channel pins and duplicates collapse."""

    page_a = uuid4()
    dense_a = uuid4()
    shared = uuid4()
    merged = merge_rerank_pins((page_a, shared), (shared, dense_a))
    assert merged == (page_a, shared, dense_a)
