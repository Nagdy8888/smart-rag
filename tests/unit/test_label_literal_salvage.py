"""Salvage exact method labels, tool descriptions, and chunking literals."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    salvage_chunking_window_values,
    salvage_method_or_heading_label,
    salvage_tool_description_string,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.release import render_verified_company_answer
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage, verifier_uid


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
        atomic_links=(
            AtomicLink(link_id="claim-1", claim=text, chunk_ids=(chunk,)),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def test_efficiency_heading_salvage_uses_query_cue() -> None:
    """Token-consumption asks salvage Lower efficiency, not another label."""

    gold = (
        "Lower efficiency\n"
        "While not always the case, multiagent systems often encounter "
        "reduced efficiency due to higher token consumption.\n"
        "Context Engineering is covered later."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "multiagent systems often encounter reduced efficiency due to "
        "higher token consumption when completing tasks.",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_method_or_heading_label(
        payload,
        fusion,
        user_query="Among multiagent challenges, what does the book say "
        "multiagent systems often encounter due to higher token consumption?",
    )
    assert salvaged.answer_text.strip().startswith("Lower efficiency")

    """A method ask with DPO evidence replaces the how-it-works paraphrase."""

    gold = (
        "Direct preference optimization\n"
        "Give both a good and a bad response per prompt and indicate "
        "the preferred one."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    wrong = verifier_uid(1)
    payload = _payload(
        "Give both a good and a bad response per prompt and indicate "
        "the preferred one.",
        chunk=wrong,
    )
    salvaged = salvage_method_or_heading_label(
        payload,
        fusion,
        user_query="In Table 7-1, what method works by giving both a good "
        "and a bad response per prompt?",
    )
    assert "Direct preference optimization" in salvaged.answer_text
    assert salvaged.citations[0].chunk_id == verifier_uid(1)


def test_tool_description_salvage_copies_exact_string() -> None:
    """A description-string ask copies Use Wolfram Alpha wording."""

    gold = (
        'tool_descriptions = {\n'
        '  "query_wolfram_alpha": "Use Wolfram Alpha to compute mathematical '
        'expressions or retrieve information.",\n'
        "}\n"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "Query Wolfram Alpha to compute expressions or retrieve information.",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_tool_description_string(
        payload,
        fusion,
        user_query="what is the description string for query_wolfram_alpha?",
    )
    assert "Use Wolfram Alpha to compute mathematical" in salvaged.answer_text


def test_chunking_window_salvage_copies_literals() -> None:
    """A window_size/overlap ask replaces off-topic memory headings."""

    gold = (
        "memory = Memory(chunking_strategy={'mode':'sliding_window', "
        "'window_size': 128, 'overlap': 16})"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "Managing Context Windows and Short-Term Memory",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_chunking_window_values(
        payload,
        fusion,
        user_query="In the Memory chunking_strategy example, what "
        "window_size and overlap values are used?",
    )
    assert "128" in salvaged.answer_text
    assert "16" in salvaged.answer_text
    assert "window_size" in salvaged.answer_text


def test_tool_description_salvage_rewrites_refused_payload() -> None:
    """A refused answer is replaced when fusion holds the Wolfram string."""

    gold = (
        'tool_descriptions = {"query_wolfram_alpha": '
        '"Use Wolfram Alpha to compute mathematical expressions."}'
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    refused = AnswerPayload(
        answer_text="",
        paragraphs=(),
        citations=(),
        atomic_links=(),
        status="refused",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    salvaged = salvage_tool_description_string(
        refused,
        fusion,
        user_query="what is the description string for query_wolfram_alpha?",
    )
    assert salvaged.status == "complete"
    assert "Use Wolfram Alpha to compute mathematical" in salvaged.answer_text
    released = render_verified_company_answer(
        salvaged, fusion=fusion, tables=()
    )
    assert released.status != "refused"
    assert released.answer_text != "Insufficient authorized evidence."


def test_chunking_salvage_rewrites_memory_heading_drift() -> None:
    """Chunking salvage replaces memory-heading drift when gold is selected."""

    gold = (
        "memory = Memory(chunking_strategy={'mode':'sliding_window',\n"
        " 'window_size': 128,\n 'overlap': 16})"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "Managing Context Windows Knowledge and Memory Short-Term Memory",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_chunking_window_values(
        payload,
        fusion,
        user_query="In the Memory chunking_strategy example, what "
        "window_size and overlap values are used?",
    )
    assert salvaged.status == "complete"
    assert "128" in salvaged.answer_text
    assert "16" in salvaged.answer_text
    assert "Managing Context Windows" not in salvaged.answer_text


def test_protocol_aspire_salvage_copies_http_span() -> None:
    """An HTTP-composability protocol ask copies the A2A aspire span."""

    gold = (
        "Much like HTTP enabled the composability of the web, A2A aspires "
        "to do the same for AI agents."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "A2A creates a shared language for multiagent coordination.",
        chunk=verifier_uid(1),
    )
    from smart_rag_core.query_answer.generate_grounded import (
        salvage_protocol_aspire_claim,
    )

    salvaged = salvage_protocol_aspire_claim(
        payload,
        fusion,
        user_query=(
            "What protocol does the book say aspires to do for AI agents "
            "what HTTP enabled for the composability of the web?"
        ),
    )
    assert "HTTP enabled the composability" in salvaged.answer_text
    assert "A2A aspires" in salvaged.answer_text
