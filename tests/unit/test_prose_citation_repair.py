"""A paraphrase with a misplaced source can be rebound without changing its words."""

from smart_rag_core.query_answer.bind_prose import rebind_high_coverage_prose
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def test_a_misplaced_memory_claim_uses_the_source_that_describes_its_predicate() -> (
    None
):
    """General topic overlap cannot crowd out the passage containing the actual details."""
    wrong = verifier_passage(1, text="Memory unit tests should check data integrity.")
    correct = verifier_passage(
        2,
        text="Memory captures prior user exchanges and state updates. This history maintains continuity across sessions.",
    )
    claim = "Memory captures prior user exchanges and state updates, maintaining history and continuity across sessions."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim",)),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim",
                claim=claim,
                chunk_ids=(wrong.chunk_id,),
                kind="fact",
                priority=1,
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=wrong.chunk_id,
                span=wrong.citation_text,
                atomic_link_id="claim",
                paragraph_index=0,
            ),
        ),
    )
    result = rebind_high_coverage_prose(payload, verifier_fusion(wrong, correct))
    assert (
        result.answer_text == payload.answer_text
        and result.paragraphs == payload.paragraphs
    )
    assert result.atomic_links[0].chunk_ids == (correct.chunk_id,)
    assert result.citations[0].span is not None
    assert result.citations[0].span in correct.citation_text
