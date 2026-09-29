"""Rebind a mis-cited function claim onto the chunk that defines it."""

from __future__ import annotations

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.release import bind_company_atomic_links
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_uid,
)

_WRONG = "Standard tool selection compares the model output with the toolset."
_RIGHT = (
    "Intro\n\n"
    "@tool def query_wolfram_alpha(expression: str) -> str:\n"
    '    """Query Wolfram Alpha to compute expressions or retrieve information."""'
    "\n\n"
    "@tool def trigger_zapier_webhook(zap_id: str) -> str:\n"
    "    pass\n"
)
_QUERY = (
    "What is the query_wolfram_alpha tool in the tool-selection example "
    "and write the snippt"
)


def _payload(cited: str) -> AnswerPayload:
    """Build the paraphrased one-claim answer that cited ``cited``.

    Args:
        cited: Chunk id the model attached to the paraphrase.

    Returns:
        Company answer with one fact claim and one citation.
    """

    claim = (
        "The `query_wolfram_alpha` tool in the tool-selection example is a tool "
        'to "compute mathematical expressions or retrieve information."'
    )
    return AnswerPayload(
        answer_text=claim,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=claim, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=cited,
                span="Standard tool selection",
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim=claim,
                chunk_ids=(cited,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def test_miscited_function_rebinds_to_the_defining_chunk() -> None:
    """A neighboring citation is replaced by the exact function definition."""

    fusion = verifier_fusion(
        verifier_passage(1, text=_WRONG, rank=2),
        verifier_passage(2, text=_RIGHT, rank=1),
    )
    wrong_id = verifier_uid(1)
    right_id = verifier_uid(2)
    bound = bind_company_atomic_links(
        _payload(wrong_id),
        fusion=fusion,
        user_query=_QUERY,
    )
    link = bound.atomic_links[0]
    assert link.chunk_ids == (right_id,)
    assert link.claim.startswith("@tool def query_wolfram_alpha")
    assert "trigger_zapier_webhook" not in link.claim
    assert bound.paragraphs[0].text == link.claim
    assert bound.citations[0].chunk_id == right_id
    assert bound.citations[0].span == link.claim
    assert link.claim in _RIGHT


def test_two_defining_chunks_are_left_unchanged() -> None:
    """Ambiguous definitions are not guessed."""

    fusion = verifier_fusion(
        verifier_passage(1, text=_WRONG, rank=2),
        verifier_passage(2, text=_RIGHT, rank=1),
        verifier_passage(3, text=_RIGHT, rank=3),
    )
    original = _payload(verifier_uid(1))
    bound = bind_company_atomic_links(
        original,
        fusion=fusion,
        user_query=_QUERY,
    )
    assert bound.atomic_links[0].claim == original.atomic_links[0].claim
    assert bound.atomic_links[0].chunk_ids == (verifier_uid(1),)


def test_definition_already_cited_is_left_unchanged() -> None:
    """A citation that already names the defining chunk is not rewritten."""

    fusion = verifier_fusion(
        verifier_passage(1, text=_WRONG, rank=2),
        verifier_passage(2, text=_RIGHT, rank=1),
    )
    original = _payload(verifier_uid(2))
    bound = bind_company_atomic_links(
        original,
        fusion=fusion,
        user_query=_QUERY,
    )
    assert bound.atomic_links[0].claim == original.atomic_links[0].claim
    assert bound.citations[0].chunk_id == verifier_uid(2)
