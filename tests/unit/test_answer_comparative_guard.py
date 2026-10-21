"""An opposite tradeoff cannot survive by sharing the right topic words."""

import pytest
from smart_rag_core.query_answer.comparative_guard import explicit_comparative_conflict
from smart_rag_core.query_answer.deterministic import deterministic_check_answer
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)

from tests.support.answer_verifier import verifier_fusion, verifier_passage


@pytest.mark.parametrize(
    ("source_text", "claim", "conflict"),
    [
        (
            "Widget benchmark has higher latency and cost.",
            "Widget benchmark reduces cost.",
            True,
        ),
        (
            "Widget benchmark has lower latency.",
            "Widget benchmark increases latency.",
            True,
        ),
        (
            "Widget benchmark latency is higher.",
            "Widget benchmark lowers latency.",
            True,
        ),
        (
            "Widget benchmark has higher latency.",
            "Widget benchmark increases latency.",
            False,
        ),
        (
            "Widget benchmark has higher latency for X and lower latency for Y.",
            "Widget benchmark lowers latency.",
            False,
        ),
        (
            "Widget benchmark does not increase latency.",
            "Widget benchmark lowers latency.",
            False,
        ),
        (
            "Widget benchmark increases latency.",
            "Widget benchmark does not reduce latency.",
            False,
        ),
    ],
)
def test_only_unambiguous_explicit_opposite_directions_are_rejected(
    source_text: str, claim: str, conflict: bool
) -> None:
    """Negation and multiple contexts stay with the semantic verifier."""
    source = verifier_passage(901, text=source_text).model_copy(
        update={"section_path": ("Widget benchmark",)}
    )
    link = AtomicLink(link_id="l1", claim=claim, chunk_ids=(source.chunk_id,))
    assert explicit_comparative_conflict(link, {source.chunk_id: source}) is conflict


def test_different_named_scope_does_not_compare_neighboring_metrics() -> None:
    """A metric word alone cannot join unrelated subjects."""
    source = verifier_passage(902, text="Another system has higher cost.")
    link = AtomicLink(
        link_id="l1",
        claim="Widget benchmark reduces cost.",
        chunk_ids=(source.chunk_id,),
    )
    assert not explicit_comparative_conflict(link, {source.chunk_id: source})


def test_contradictory_paragraph_is_removed_before_model_verification() -> None:
    """Canonical source text, valid IDs, and correct topic are insufficient."""
    text = "Widget benchmark has higher latency and cost."
    source = verifier_passage(903, text=text).model_copy(
        update={"section_path": ("Widget benchmark",)}
    )
    bad = "Widget benchmark reduces cost."
    good = "Widget benchmark has higher latency and cost."
    links = tuple(
        AtomicLink(link_id=lid, claim=claim, chunk_ids=(source.chunk_id,))
        for lid, claim in (("bad", bad), ("good", good))
    )
    payload = AnswerPayload(
        answer_text=bad + "\n\n" + good,
        paragraphs=tuple(
            AnswerParagraph(
                paragraph_index=i, text=link.claim, link_ids=(link.link_id,)
            )
            for i, link in enumerate(links)
        ),
        atomic_links=links,
        citations=tuple(
            AnswerCitation(
                chunk_id=source.chunk_id,
                span=text,
                atomic_link_id=link.link_id,
                paragraph_index=i,
            )
            for i, link in enumerate(links)
        ),
    )
    result, failures = deterministic_check_answer(
        payload, fusion=verifier_fusion(source), tables=(), require_paragraphs=True
    )
    assert "unsupported_comparative_direction" in failures
    assert bad not in result.answer_text
    assert [link.link_id for link in result.atomic_links] == ["good"]
    assert "bad" in result.refused_links
    assert result.status == "partial"
