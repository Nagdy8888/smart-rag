"""Source matches must preserve question identity and generated explanations."""

from smart_rag_core.query_answer.format_shape import format_requested_answer_shape
from smart_rag_core.query_answer.generate_anchor_salvage import (
    salvage_anchor_claim_fill,
)
from smart_rag_core.query_answer.generate_code_salvage import salvage_named_table_block
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.release import bind_company_atomic_links

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def test_code_formatting_preserves_explanation_and_citation_ownership() -> None:
    """Formatting a snippet never removes the following explanation."""
    paragraphs = (
        AnswerParagraph(
            paragraph_index=0,
            text="def run_widget():\n    return 1",
            link_ids=("code",),
        ),
        AnswerParagraph(
            paragraph_index=1,
            text="**How it works**\nThe function returns a constant.",
            link_ids=("explanation",),
        ),
    )
    citations = tuple(
        AnswerCitation(
            chunk_id=str(i),
            span="source",
            atomic_link_id=p.link_ids[0],
            paragraph_index=i,
        )
        for i, p in enumerate(paragraphs)
    )
    payload = AnswerPayload(
        answer_text="\n\n".join(p.text for p in paragraphs),
        paragraphs=paragraphs,
        citations=citations,
    )
    result = format_requested_answer_shape(
        payload,
        user_query="Reproduce run_widget in a fenced Python block and explain it.",
    )
    assert len(result.paragraphs) == 2
    assert "```python" in result.answer_text
    assert paragraphs[1].text in result.answer_text
    assert result.citations == citations


def test_heading_only_citation_uses_body_from_the_same_canonical_record() -> None:
    """A repeated heading cannot stand in for its supporting passage."""
    passage = verifier_passage(
        1,
        text="Knowledge and Memory\n\nKnowledge supplies external facts. Memory retains past interactions.",
    ).model_copy(update={"section_path": ("Knowledge and Memory",)})
    payload = AnswerPayload(
        answer_text="Memory retains interactions.",
        paragraphs=(
            AnswerParagraph(
                paragraph_index=0,
                text="Memory retains interactions.",
                link_ids=("claim",),
            ),
        ),
        atomic_links=(
            AtomicLink(
                link_id="claim",
                claim="Memory retains interactions.",
                chunk_ids=(passage.chunk_id,),
                kind="fact",
                priority=1,
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id=passage.chunk_id,
                span="Knowledge and Memory",
                paragraph_index=0,
                atomic_link_id="claim",
            ),
        ),
    )
    result = bind_company_atomic_links(
        payload, fusion=verifier_fusion(passage), user_query="Explain memory."
    )
    assert result.citations[0].span != "Knowledge and Memory"
    assert result.citations[0].span is not None
    assert result.citations[0].span in passage.citation_text


def test_absent_requested_year_cannot_release_unrelated_price_example() -> None:
    """Shared price words cannot replace a missing edition identifier."""
    payload = AnswerPayload(
        answer_text="Insufficient authorized evidence.", status="refused"
    )
    fusion = verifier_fusion(
        verifier_passage(
            1,
            text="The retail price for this order is 39.99. The release date is recorded.",
        )
    )
    assert (
        salvage_anchor_claim_fill(
            payload,
            fusion,
            user_query="State the retail price and release date of the 2031 edition.",
        )
        is payload
    )


def test_named_person_cannot_be_replaced_by_shared_company_words() -> None:
    """An unmatched person remains unsupported despite topical overlap."""
    payload = AnswerPayload(
        answer_text="Insufficient authorized evidence.", status="refused"
    )
    fusion = verifier_fusion(
        verifier_passage(1, text="The company annual review discusses salary policies.")
    )
    assert (
        salvage_anchor_claim_fill(
            payload,
            fusion,
            user_query="What is Morgan's exact annual salary in the company?",
        )
        is payload
    )


def test_table_reference_keeps_translated_explanation() -> None:
    """A table used as evidence must not overwrite Arabic narrative."""
    paragraph = AnswerParagraph(
        paragraph_index=0,
        text="**مقارنة التخزين**\nقواعد البيانات تدعم الاستعلامات، بينما تخزين الكائنات مناسب للملفات.",  # noqa: RUF001 - Arabic language fixture
        link_ids=("claim-1",),
    )
    payload = AnswerPayload(
        answer_text=paragraph.text, paragraphs=(paragraph,), status="complete"
    )
    fusion = verifier_fusion(
        verifier_passage(
            1,
            text="Table 8-1. Storage\n| Approach | Pros |\n| --- | --- |\n| SQL | Queryable |\n| Objects | Durable |",
        )
    )
    assert (
        salvage_named_table_block(
            payload,
            fusion,
            user_query="Explain in Arabic the tradeoffs from Table 8-1.",
        )
        is payload
    )
