"""Release retains owned spans and does not inflate bookkeeping source IDs."""

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.release import (
    bind_company_atomic_links,
    render_verified_company_answer,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage

from tests.support.answer_verifier import verified_answer_state, verifier_passage


def test_six_claims_with_two_owned_citations_do_not_grow_to_eighteen() -> None:
    """A third bookkeeping source per claim must not trigger a paid-run refusal."""
    base = FusionResult.model_validate(verified_answer_state()["fusion"])
    passages: list[ScoredPassage] = []
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    links: list[AtomicLink] = []
    for index in range(6):
        sources = [
            verifier_passage(
                600 + index * 3 + j,
                text=f"signal{index} reading high, with corroborating evidence.",
            )
            for j in range(3)
        ]
        passages.extend(sources)
        text = f"the reading for signal{index} is elevated."
        link_id = f"claim-{index}"
        paragraphs.append(
            AnswerParagraph(paragraph_index=index, text=text, link_ids=(link_id,))
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=text,
                chunk_ids=tuple(s.chunk_id for s in sources),
                priority=index,
            )
        )
        citations.extend(
            AnswerCitation(
                chunk_id=s.chunk_id,
                span=s.citation_text,
                atomic_link_id=link_id,
                paragraph_index=index,
            )
            for s in sources[:2]
        )
    payload = AnswerPayload(
        answer_text="\n\n".join(p.text for p in paragraphs),
        paragraphs=tuple(paragraphs),
        citations=tuple(citations),
        atomic_links=tuple(links),
        status="complete",
    )
    result = render_verified_company_answer(
        payload, fusion=base.model_copy(update={"evidence": tuple(passages)}), tables=()
    )
    assert len(result.citations) == 12
    assert {c.chunk_id for c in result.citations} == {c.chunk_id for c in citations}
    assert result.paragraphs == payload.paragraphs


def test_multiple_owned_spans_in_one_chunk_survive_release() -> None:
    """A dictionary keyed only by source/link must not overwrite an earlier span."""
    base = FusionResult.model_validate(verified_answer_state()["fusion"])
    source = verifier_passage(
        700, text="The gauge starts at seven. The gauge ends at eight."
    )
    claim = "the gauge rises between its initial and final readings."
    spans = ("The gauge starts at seven.", "The gauge ends at eight.")
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        atomic_links=(
            AtomicLink(link_id="claim-1", claim=claim, chunk_ids=(source.chunk_id,)),
        ),
        citations=tuple(
            AnswerCitation(
                chunk_id=source.chunk_id,
                span=s,
                atomic_link_id="claim-1",
                paragraph_index=0,
            )
            for s in spans
        ),
        status="complete",
    )
    result = render_verified_company_answer(
        payload, fusion=base.model_copy(update={"evidence": (source,)}), tables=()
    )
    assert tuple(c.span for c in result.citations) == spans


def test_inference_link_keeps_every_required_source() -> None:
    """Fact bookkeeping cleanup cannot weaken a multi-source inference chain."""
    base = FusionResult.model_validate(verified_answer_state()["fusion"])
    left = verifier_passage(701, text="First relation links the two widgets.")
    right = verifier_passage(702, text="Second relation links a widget to the result.")
    claim = "the first relation combines with the second relation."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("step-1",)),
        ),
        atomic_links=(
            AtomicLink(
                link_id="step-1",
                claim=claim,
                chunk_ids=(left.chunk_id, right.chunk_id),
                kind="inference_link",
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=left.chunk_id,
                span=left.citation_text,
                atomic_link_id="step-1",
                paragraph_index=0,
                inference=True,
            ),
        ),
        status="complete",
    )
    result = render_verified_company_answer(
        payload, fusion=base.model_copy(update={"evidence": (left, right)}), tables=()
    )
    assert {c.chunk_id for c in result.citations} == {left.chunk_id, right.chunk_id}


def test_token_rebind_does_not_add_a_third_citation_to_one_fact() -> None:
    """Two owned sources leave no capacity for an optional naming holder."""
    base = FusionResult.model_validate(verified_answer_state()["fusion"])
    first = verifier_passage(710, text="alpha_route returns a result.", rank=1)
    other = verifier_passage(711, text="beta_route returns a result.", rank=3)
    naming = verifier_passage(712, text="alpha_route is another route.", rank=2)
    claim = "alpha_route selects the same result as beta_route."
    payload = AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(naming.chunk_id, other.chunk_id),
            ),
        ),
        citations=tuple(
            AnswerCitation(
                chunk_id=s.chunk_id,
                span=s.citation_text,
                paragraph_index=0,
                atomic_link_id="claim-1",
            )
            for s in (naming, other)
        ),
        status="complete",
    )
    result = bind_company_atomic_links(
        payload, fusion=base.model_copy(update={"evidence": (first, other, naming)})
    )
    assert len(result.citations) == 2
    assert any(c.chunk_id == other.chunk_id for c in result.citations)
