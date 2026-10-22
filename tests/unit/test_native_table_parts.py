"""A multi-page native table must keep all rows and cite each original fragment."""

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.native_table_parts import copy_native_table_parts

from tests.support.answer_verifier import verifier_passage


def test_adjacent_table_fragments_keep_rows_and_independent_citations() -> None:
    """Two matching table fragments form one answer without losing the second page."""
    first = verifier_passage(
        1, text="| Model | Hardware |\n| --- | --- |\n| Small | RTX |"
    )
    first = first.model_copy(update={"content_kind": "table", "page_number": 44})
    second = verifier_passage(
        2, text="| Model | Hardware |\n| --- | --- |\n| Large | 4xA100 |"
    )
    second = second.model_copy(
        update={
            "document_id": first.document_id,
            "version_id": first.version_id,
            "content_kind": "table",
            "page_number": 45,
        }
    )
    unrelated = verifier_passage(
        3, text="| Model | Hardware |\n| --- | --- |\n| Secret | Other |"
    )
    unrelated = unrelated.model_copy(update={"page_number": 45})
    result = copy_native_table_parts(
        AnswerPayload(answer_text="", status="refused"), [first, second, unrelated]
    )
    assert result is not None and result.status == "complete"
    assert "Small" in result.answer_text and "4xA100" in result.answer_text
    assert "Secret" not in result.answer_text
    assert {c.chunk_id for c in result.citations} == {first.chunk_id, second.chunk_id}
    assert len({link.link_id for link in result.atomic_links}) == len(
        result.atomic_links
    )


def test_a_different_header_on_the_next_page_is_not_the_same_table() -> None:
    """Page proximity cannot merge unrelated table schemas."""
    first = verifier_passage(
        1, text="| Model | Hardware |\n| --- | --- |\n| Small | RTX |"
    )
    first = first.model_copy(update={"page_number": 44})
    other = first.model_copy(
        update={
            "chunk_id": "00000002-0000-4000-8000-000000000000",
            "page_number": 45,
            "citation_text": "| Model | Price |\n| --- | --- |\n| Other | 999 |",
        }
    )
    result = copy_native_table_parts(AnswerPayload(answer_text=""), [first, other])
    assert result is not None and "999" not in result.answer_text
