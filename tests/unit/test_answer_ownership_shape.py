"""Scoped ownership questions preserve source column assignments before checking."""

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.native_blocks import attach_native_evidence
from smart_rag_core.query_answer.ownership_shape import shape_ownership_matrix_draft
from smart_rag_core.query_answer.query_coverage import salvage_question_coverage
from smart_rag_core.query_fusion.models import FusionResult

from tests.support.answer_verifier import verified_answer_state, verifier_passage


def test_scoped_matrix_replaces_unverified_paraphrase_with_exact_cells() -> None:
    """A model cannot move a responsibility to a neighboring role column."""
    state = verified_answer_state()
    draft = AnswerPayload.model_validate(state["answer"])
    source = verifier_passage(
        601,
        text=(
            "Governance | 111\nIncident recovery responsibility assignment matrix (RACI).\n"
            "| Activity | Operator | Reviewer |\n| --- | --- | --- |\n"
            "| Restore | R | A |\n| Audit | I | R |"
        ),
    )
    fusion = FusionResult.model_validate(state["fusion"]).model_copy(
        update={"evidence": (source,)}
    )
    query = "Which incident recovery responsibilities belong to each role?"
    result = shape_ownership_matrix_draft(draft, fusion, user_query=query)
    assert result.answer_text == source.citation_text.split("\n", 2)[2]
    assert "| Restore | R | A |" in result.answer_text
    assert all(c.span in source.citation_text for c in result.citations if c.span)
    assert all(c.chunk_id == source.chunk_id for c in result.citations)
    assert len(result.paragraphs) <= 6 and len(result.citations) <= 12
    native = source.model_copy(update={"content_kind": "table"})
    attached = attach_native_evidence(
        result, fusion.model_copy(update={"evidence": (native,)}), user_query=query
    )
    assert attached.answer_text == result.answer_text
    assert salvage_question_coverage(result, fusion, user_query=query) == result


def test_generic_or_different_scope_does_not_replace_draft() -> None:
    """Neither a generic role ask nor unrelated scope selects this matrix."""
    state = verified_answer_state()
    draft = AnswerPayload.model_validate(state["answer"])
    source = verifier_passage(
        602,
        text="Incident recovery RACI.\n| Role | Duty |\n| --- | --- |\n| A | Retry |",
    )
    fusion = FusionResult.model_validate(state["fusion"]).model_copy(
        update={"evidence": (source,)}
    )
    for query in (
        "Which responsibilities belong to each role?",
        "Which release deployment responsibilities belong to each role?",
        "Explain incident recovery.",
    ):
        assert shape_ownership_matrix_draft(draft, fusion, user_query=query) is draft


def test_full_matrix_beats_a_captioned_page_continuation() -> None:
    """A higher ranked continuation cannot replace the full fitted assignment."""
    state = verified_answer_state()
    draft = AnswerPayload.model_validate(state["answer"])
    prefix = "Incident recovery RACI.\n| Activity | Operator |\n| --- | --- |\n"
    continuation = verifier_passage(603, text=prefix + "| Audit | I |")
    full = verifier_passage(604, text=prefix + "| Restore | R |\n| Audit | I |")
    fusion = FusionResult.model_validate(state["fusion"]).model_copy(
        update={"evidence": (continuation, full)}
    )
    query = "Which incident recovery responsibilities belong to each role?"
    result = shape_ownership_matrix_draft(draft, fusion, user_query=query)
    assert "| Restore | R |" in result.answer_text
    assert result.answer_text.count("| Audit | I |") == 1
    assert salvage_question_coverage(result, fusion, user_query=query) == result
