"""Anchor-gated extractive claim fill for omitted draft spans."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    salvage_anchor_claim_fill,
    salvage_named_code_definition,
    salvage_named_page_claim_fill,
)
from smart_rag_core.query_answer.generate_page_openings import fill_cited_page_opening
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
        link for link in salvaged.atomic_links if link.link_id == "page-opening-1"
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


def test_anchor_claim_fill_keeps_a_short_code_block() -> None:
    """A short def already covers the page opening, so the payload stays."""

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


def test_exact_wording_page_ask_appends_passage_opening() -> None:
    """A cited-page exact-wording ask copies the passage opening."""

    passage = verifier_passage(
        7,
        text=(
            "The ledger records a final balance before any later note.\n"
            "A handshake token appears only in this later sentence."
        ),
    )
    passage = passage.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(passage)
    payload = _payload("Setup is required.", chunk=passage.chunk_id)
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "What exact wording does page 12 use for the main claim "
            "about the handshake token? Use only that document."
        ),
    )
    claim = next(
        link for link in salvaged.atomic_links if link.link_id == "page-opening-1"
    )
    assert "final balance" in claim.claim.casefold()
    assert "\n" not in claim.claim
    citation = next(
        item for item in salvaged.citations if item.atomic_link_id == "page-opening-1"
    )
    assert citation.span is not None
    assert citation.span in passage.citation_text


def test_ordinary_page_ask_keeps_anchor_neighborhood() -> None:
    """A page ask that is not a source-word ask still uses topic anchors."""

    passage = verifier_passage(
        8,
        text=(
            "The ledger records a final balance before any later note. "
            "A handshake token appears only in this later sentence."
        ),
    )
    passage = passage.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(passage)
    payload = _payload("Setup is required.", chunk=passage.chunk_id)
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "On page 12, what does the handshake token require? Use only that document."
        ),
    )
    claim = next(
        link for link in salvaged.atomic_links if link.link_id == "anchor-claim-1"
    )
    assert "handshake token" in claim.claim.casefold()
    assert "final balance" not in claim.claim.casefold()


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


def test_exact_wording_page_ask_copies_every_page_opening() -> None:
    """Both fitted passages on the named page contribute an opening."""

    overlap = verifier_passage(
        9,
        text="The catalog lists every handshake token in a later section.",
        rank=1,
    )
    overlap = overlap.model_copy(update={"page_number": 12})
    holder = verifier_passage(
        10,
        text="The ledger records a final balance before any later note.",
        rank=2,
    )
    holder = holder.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(overlap, holder)
    payload = _payload("Setup is required.", chunk=overlap.chunk_id)
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "What exact wording does page 12 use for the handshake token "
            "catalog? Use only that document."
        ),
    )
    openings = {
        link.link_id: link
        for link in salvaged.atomic_links
        if link.link_id.startswith("page-opening-")
    }
    assert len(openings) == 2
    by_chunk = {link.chunk_ids[0]: link for link in openings.values()}
    assert overlap.chunk_id in by_chunk
    assert holder.chunk_id in by_chunk
    for passage in (overlap, holder):
        citation = next(
            item
            for item in salvaged.citations
            if item.chunk_id == passage.chunk_id and item.atomic_link_id in openings
        )
        assert citation.span is not None
        assert citation.span in passage.citation_text
    assert "final balance" in salvaged.answer_text.casefold()


def test_existing_anchor_claim_still_gains_the_other_opening() -> None:
    """An anchor claim on one page chunk does not block the other opening."""

    overlap = verifier_passage(
        11,
        text="The catalog lists every handshake token in a later section.",
        rank=1,
    )
    overlap = overlap.model_copy(update={"page_number": 12})
    holder = verifier_passage(
        12,
        text="The ledger records a final balance before any later note.",
        rank=2,
    )
    holder = holder.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(overlap, holder)
    opening = overlap.citation_text
    payload = AnswerPayload(
        answer_text=opening,
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text=opening,
                link_ids=("anchor-claim-1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=overlap.chunk_id,
                span=opening,
                paragraph_index=0,
                atomic_link_id="anchor-claim-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="anchor-claim-1",
                claim=opening,
                chunk_ids=(overlap.chunk_id,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "What exact wording does page 12 use for the handshake token "
            "catalog? Use only that document."
        ),
    )
    assert any(link.link_id == "anchor-claim-1" for link in salvaged.atomic_links)
    gained = next(
        link for link in salvaged.atomic_links if link.link_id == "page-opening-1"
    )
    assert gained.chunk_ids == (holder.chunk_id,)
    citation = next(
        item for item in salvaged.citations if item.atomic_link_id == "page-opening-1"
    )
    assert citation.span is not None
    assert citation.span in holder.citation_text
    assert "final balance" in salvaged.answer_text.casefold()


def _long_page_text() -> str:
    """Build a passage whose opening ends before the following characters.

    Returns:
        Text longer than the citation cap, with one sentence boundary inside
        the opening window.
    """

    return "The ledger records a final balance. " + ("a" * 1100)


def test_source_word_ask_appends_the_continuation() -> None:
    """A passage longer than 1,000 characters stays one paragraph."""

    text = _long_page_text()
    passage = verifier_passage(13, text=text)
    passage = passage.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(passage)
    payload = _payload("Setup is required.", chunk=passage.chunk_id)
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "What exact wording does page 12 use for the main claim? "
            "Use only that document."
        ),
    )
    openings = [
        link
        for link in salvaged.atomic_links
        if link.link_id.startswith("page-opening-")
    ]
    assert len(openings) == 1
    citation = next(
        item
        for item in salvaged.citations
        if item.atomic_link_id == openings[0].link_id
    )
    assert citation.span is not None
    assert citation.span in text
    assert len(citation.span) <= 1000
    paragraph = next(
        item
        for item in salvaged.paragraphs
        if openings[0].link_id in item.link_ids
    )
    assert "The ledger records a final balance." in paragraph.text
    assert "a" * 1100 in paragraph.text


def test_code_block_keeps_the_continuation() -> None:
    """An existing code-definition link does not suppress the continuation."""

    text = _long_page_text()
    passage = verifier_passage(14, text=text)
    passage = passage.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(passage)
    code_claim = "def cancel_order(order_id: str) -> None:"
    payload = AnswerPayload(
        answer_text=code_claim,
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text=code_claim,
                link_ids=("code-def-1",),
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=passage.chunk_id,
                span=code_claim,
                paragraph_index=0,
                atomic_link_id="code-def-1",
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="code-def-1",
                claim=code_claim,
                chunk_ids=(passage.chunk_id,),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "On page 12, reproduce the cancel_order listing as a fenced "
            "Python code block. Use only that document."
        ),
    )
    assert any(link.link_id == "code-def-1" for link in salvaged.atomic_links)
    openings = [
        link
        for link in salvaged.atomic_links
        if link.link_id.startswith("page-opening-")
    ]
    assert len(openings) == 1
    assert openings[0].priority == 0
    paragraph = next(
        item
        for item in salvaged.paragraphs
        if openings[0].link_id in item.link_ids
    )
    assert "a" * 1100 in paragraph.text


def test_table_reproduce_ask_does_not_gain_page_windows() -> None:
    """A table reproduce ask keeps the anchor path and skips page windows."""

    text = _long_page_text()
    passage = verifier_passage(15, text=text)
    passage = passage.model_copy(update={"page_number": 12})
    fusion = verifier_fusion(passage)
    payload = _payload("Setup is required.", chunk=passage.chunk_id)
    salvaged = salvage_anchor_claim_fill(
        payload,
        fusion,
        user_query=(
            "On page 12, reproduce Table 2-1 as a Markdown pipe table. "
            "Use only that document."
        ),
    )
    assert all(
        not link.link_id.startswith("page-opening-") for link in salvaged.atomic_links
    )


def test_cited_page_windows_reach_past_the_second_span() -> None:
    """A statement past the old 1,000-character cut stays in one paragraph."""

    marker = "UNIQUE-MARKER"
    text = ("x" * 2100) + marker + ("y" * 100)
    passage = verifier_passage(16, text=text)
    passage = passage.model_copy(update={"page_number": 4})
    fusion = verifier_fusion(passage)
    payload = _payload("A short draft.", chunk=passage.chunk_id)
    released = fill_cited_page_opening(
        payload,
        fusion,
        user_query="What exact wording does page 4 give? Use only that document.",
    )
    assert released is not None
    assert marker in released.answer_text
    openings = [
        link.link_id
        for link in released.atomic_links
        if link.link_id.startswith("page-opening-")
    ]
    assert len(openings) == 1
    for citation in released.citations:
        if citation.atomic_link_id in openings and citation.span:
            assert citation.span in text
