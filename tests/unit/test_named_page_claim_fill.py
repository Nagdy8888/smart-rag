"""Anchor-gated extractive claim fill for omitted draft spans."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    salvage_anchor_claim_fill,
    salvage_named_code_definition,
    salvage_named_page_claim_fill,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def _payload(text: str, *, chunk: str) -> AnswerPayload:
    """Build a one-claim answer citing ``chunk``.

    Args:
        text: Claim prose.
        chunk: Cited chunk id.

    Returns:
        Complete company answer payload.
    """

    return AnswerPayload(
        answer_text=text,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=text, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk,
                span=text[:40],
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(AtomicLink(link_id="claim-1", claim=text, chunk_ids=(chunk,)),),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def test_anchor_claim_fill_without_named_page() -> None:
    """Two query anchors in fitted evidence still fill without a page cite."""

    passage = verifier_passage(
        1,
        text=(
            "The protocol requires a handshake token before any agent "
            "may publish a tool result."
        ),
    )
    fusion = verifier_fusion(passage)
    payload = _payload(
        "Agents can publish results after setup.",
        chunk=passage.chunk_id,
    )
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "Quote the wording about the handshake token before a "
            "tool result. Use only that document."
        ),
    )
    assert salvaged is not payload
    assert any(link.link_id == "anchor-claim-1" for link in salvaged.atomic_links)
    assert "handshake token" in salvaged.answer_text.casefold()


def test_anchor_claim_fill_prefers_named_page_passage() -> None:
    """When pages are cited, the matching page passage is preferred."""

    other = verifier_passage(
        2,
        text="Unrelated handshake token noise on another page.",
    )
    other = other.model_copy(update={"page_number": 1})
    target = verifier_passage(
        3,
        text=(
            "The protocol requires a handshake token before any agent "
            "may publish a tool result."
        ),
    )
    target = target.model_copy(update={"page_number": 27})
    fusion = verifier_fusion(other, target)
    payload = _payload("Setup is required.", chunk=other.chunk_id)
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "On page 27, quote the wording about the handshake token "
            "before a tool result. Use only that document."
        ),
    )
    assert salvaged is not payload
    claim = next(
        link for link in salvaged.atomic_links if link.link_id == "anchor-claim-1"
    )
    assert target.chunk_id in claim.chunk_ids


def test_page_wrapper_delegates_to_anchor_fill() -> None:
    """Cycle 4 wrapper still fills a cited-page omit."""

    passage = verifier_passage(
        4,
        text=(
            "The protocol requires a handshake token before any agent "
            "may publish a tool result."
        ),
    )
    passage = passage.model_copy(update={"page_number": 27})
    fusion = verifier_fusion(passage)
    payload = _payload(
        "Agents can publish results after setup.",
        chunk=passage.chunk_id,
    )
    salvaged = salvage_named_page_claim_fill(
        payload,
        fusion,
        user_query=(
            "On page 27, quote the wording about the handshake token "
            "before a tool result. Use only that document."
        ),
    )
    assert salvaged is not payload
    assert "handshake token" in salvaged.answer_text.casefold()


def test_anchor_claim_fill_skips_after_structural_salvage() -> None:
    """Code-definition salvage link blocks anchor claim fill."""

    code = (
        "def cancel_order(order_id: str) -> None:\n"
        '    """Cancel one open order."""\n'
        "    return None\n"
    )
    passage = verifier_passage(5, text=code)
    passage = passage.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(passage)
    empty = AnswerPayload(
        answer_text="",
        paragraphs=(),
        citations=(),
        atomic_links=(),
        status="refused",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    structural = salvage_named_code_definition(
        empty,
        fusion,
        user_query=(
            "On page 12, reproduce the cancel_order tool definition "
            "as a fenced Python code block. Use only that document."
        ),
    )
    assert any(link.link_id == "code-def-1" for link in structural.atomic_links)
    again = salvage_anchor_claim_fill(
        structural,
        fusion,
        user_query=(
            "On page 12, reproduce the cancel_order tool definition "
            "as a fenced Python code block. Use only that document."
        ),
    )
    assert again is structural


def test_anchor_claim_fill_noop_when_span_already_present() -> None:
    """Draft that already holds the span is left unchanged."""

    body = (
        "The protocol requires a handshake token before any agent "
        "may publish a tool result."
    )
    passage = verifier_passage(6, text=body)
    passage = passage.model_copy(update={"page_number": 27})
    fusion = verifier_fusion(passage)
    payload = _payload(body, chunk=passage.chunk_id)
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "On page 27, quote the wording about the handshake token. "
            "Use only that document."
        ),
    )
    assert salvaged is payload
