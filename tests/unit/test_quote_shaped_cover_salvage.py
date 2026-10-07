"""Quote-shaped extractive cover for code-fence and pipe-table asks."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    quote_shaped_anchors,
    salvage_quote_shaped_cover,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.retrieval.rerank import code_definition_gold_pattern

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


def test_quote_shaped_anchors_from_including_clause() -> None:
    """Including-row asks expose both row labels as anchors."""

    query = (
        "In the company document Building Applications with AI Agents, "
        "reproduce Table 10-1 (Taxonomy of metrics) as a Markdown pipe table "
        "including the Hallucination indicator and Task abandonment rate rows. "
        "Use only that document."
    )
    anchors = quote_shaped_anchors(query)
    joined = " | ".join(anchors).casefold()
    assert "hallucination indicator" in joined
    assert "task abandonment rate" in joined
    assert "Table 10-1" in anchors or "table 10-1" in joined


def test_code_definition_pattern_matches_class() -> None:
    """PascalCase identifiers match ``class Name`` in evidence."""

    pattern = code_definition_gold_pattern(("SupplyChainWorkflow", "manage_inventory"))
    assert pattern is not None
    text = "class SupplyChainWorkflow:\n    pass\ndef manage_inventory():\n    return 1"
    assert pattern.search(text) is not None


def test_salvage_quote_cover_replaces_paraphrase_with_multi_anchor_span() -> None:
    """Code-fence asks release one span covering class and activity string."""

    chunk = "c-quote-1"
    evidence = (
        "prelude\n"
        "class SupplyChainWorkflow:\n"
        "    async def run(self):\n"
        '        await workflow.execute_activity("inventory_activity", ...)\n'
        "trailer\n"
    )
    fusion = verifier_fusion(verifier_passage(1, text=evidence))
    # Force the fusion chunk id used by salvage.
    fusion = fusion.model_copy(
        update={
            "evidence": (
                fusion.evidence[0].model_copy(update={"chunk_id": chunk}),
            )
        }
    )
    query = (
        "In the company document Building Applications with AI Agents, "
        "reproduce the SupplyChainWorkflow class definition line and the "
        "inventory_activity execute_activity call as a fenced Python code "
        "block. Use only that document."
    )
    prior = _payload(
        "The workflow class manages inventory activities.",
        chunk=chunk,
    )
    updated = salvage_quote_shaped_cover(prior, fusion, user_query=query)
    body = " ".join(link.claim for link in updated.atomic_links)
    assert "class SupplyChainWorkflow" in body
    assert "inventory_activity" in body


def test_salvage_quote_cover_skips_prose_asks() -> None:
    """Conceptual asks without fence/table shape stay model-authored."""

    chunk = "c-quote-2"
    fusion = verifier_fusion(
        verifier_passage(1, text="Hallucination indicator is a metric.")
    )
    fusion = fusion.model_copy(
        update={
            "evidence": (
                fusion.evidence[0].model_copy(update={"chunk_id": chunk}),
            )
        }
    )
    query = (
        "In the company document Building Applications with AI Agents, "
        "what is a hallucination indicator? Use only that document."
    )
    prior = _payload("A hallucination indicator tracks invented claims.", chunk=chunk)
    updated = salvage_quote_shaped_cover(prior, fusion, user_query=query)
    assert updated is prior
