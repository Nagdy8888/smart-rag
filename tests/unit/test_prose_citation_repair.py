"""A paraphrase with a misplaced source can be rebound without changing its words."""

from smart_rag_core.query_answer.bind_prose import rebind_high_coverage_prose
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def test_unique_long_literal_repairs_a_lower_overlap_paraphrase() -> None:
    """An exact distinctive phrase can identify the source without changing the claim."""
    wrong = verifier_passage(1, text="A history unit checks exchange continuity.")
    correct = verifier_passage(
        2,
        text="The archive needs separate indexing or tracking systems. Its access latency is a trade-off.",
    )
    claim = "Archive access needs separate indexing or tracking systems, so frequent queries add latency and extra infrastructure."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim",)),
        ),
        atomic_links=(
            AtomicLink(link_id="claim", claim=claim, chunk_ids=(wrong.chunk_id,)),
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
    assert result.answer_text == payload.answer_text
    assert result.atomic_links[0].claim == claim
    assert result.atomic_links[0].chunk_ids == (correct.chunk_id,)
    assert result.citations[0].span is not None
    assert result.citations[0].span in correct.citation_text
    # A paraphrase is still subject to the normal verifier, including polarity.
    from smart_rag_core.query_answer.models import VerifierLinkVerdict, VerifierPayload
    from smart_rag_core.query_answer.verifier import run_verifier_batch

    def reject(links: tuple[AtomicLink, ...]) -> VerifierPayload:
        """Reject the unsupported inference; citation repair is not a support vote."""
        return VerifierPayload(
            link_verdicts=tuple(
                VerifierLinkVerdict(
                    link_id=x.link_id, supported=False, reason="unsupported"
                )
                for x in links
            )
        )

    checked, calls, _omitted = run_verifier_batch(
        result, caller=reject, already_called=0, fusion=verifier_fusion(wrong, correct)
    )
    assert calls == 1
    assert checked.status == "refused"


def test_ambiguous_long_phrase_is_not_guessed() -> None:
    """Two sources holding the same literal leave an uncertain binding unchanged."""
    wrong = verifier_passage(1, text="History continuity only.")
    text = "The archive needs separate indexing or tracking systems. Access latency is a trade-off."
    claim = "Archive access needs separate indexing or tracking systems, with extra latency and infrastructure for frequent queries."
    payload = AnswerPayload(
        atomic_links=(
            AtomicLink(link_id="claim", claim=claim, chunk_ids=(wrong.chunk_id,)),
        )
    )
    assert (
        rebind_high_coverage_prose(
            payload,
            verifier_fusion(
                wrong, verifier_passage(2, text=text), verifier_passage(3, text=text)
            ),
        )
        == payload
    )


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
