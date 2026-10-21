"""Missing facets use exact fitted evidence without restoring rejected prose."""

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.native_blocks import attach_native_evidence
from smart_rag_core.query_answer.query_coverage import (
    narrative_claim_limit,
    salvage_question_coverage,
)
from smart_rag_core.query_fusion.models import FusionResult

from tests.support.answer_verifier import verified_answer_state, verifier_passage


def test_second_question_gets_an_exact_source_paragraph() -> None:
    """Coverage favors a paragraph covering the complete second question."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    source = verifier_passage(
        501,
        text=(
            "Queues persist when enabled; this sentence omits the recovery mechanism."
            "\n\nQueue recovery uses saved offsets, allowing queues to persist after crashes."
        ),
    )
    fusion = FusionResult.model_validate(state["fusion"]).model_copy(
        update={"evidence": (source,)}
    )
    result = salvage_question_coverage(
        payload,
        fusion,
        user_query="Explain widgets, and how do queues persist after crashes?",
    )
    assert "Queue recovery uses saved offsets" in result.answer_text
    assert all(p in result.paragraphs for p in payload.paragraphs)
    span = result.citations[-1].span
    assert span is not None and span in source.citation_text
    assert (
        salvage_question_coverage(
            result,
            fusion,
            user_query="Explain widgets, and how do queues persist after crashes?",
        )
        == result
    )


def test_responsibility_table_is_copied_only_from_a_cited_source() -> None:
    """No neighboring uncited role table is appended to an answer."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    fusion = FusionResult.model_validate(state["fusion"])
    cited = fusion.evidence[0].model_copy(
        update={
            "citation_text": "| Role | Duty |\n| --- | --- |\n| A | Retry monitoring |\n| B | Cost review |"
        }
    )
    other = verifier_passage(
        502, text="| Role | Duty |\n| --- | --- |\n| Wrong | Unrelated |"
    )
    fusion = fusion.model_copy(update={"evidence": (other, cited)})
    result = salvage_question_coverage(
        payload, fusion, user_query="Which responsibilities belong to each role?"
    )
    assert "Cost review" in result.answer_text
    assert "Unrelated" not in result.answer_text
    assert all(p in result.paragraphs for p in payload.paragraphs)
    assert all(c in result.citations for c in payload.citations)
    native = cited.model_copy(update={"content_kind": "table"})
    repeated = attach_native_evidence(
        result,
        fusion.model_copy(update={"evidence": (native,)}),
        user_query="Which responsibilities belong to each role?",
    )
    assert repeated.answer_text == result.answer_text


def test_full_paragraph_capacity_keeps_checked_answer_and_marks_partial() -> None:
    """Exact-table additions cannot evict already checked paragraphs."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    payload = payload.model_copy(
        update={
            "paragraphs": tuple(
                payload.paragraphs[0].model_copy(update={"paragraph_index": i})
                for i in range(6)
            )
        }
    )
    fusion = FusionResult.model_validate(state["fusion"])
    cited = fusion.evidence[0].model_copy(
        update={
            "citation_text": "| Role | Duty |\n| --- | --- |\n| A | Retry monitoring |"
        }
    )
    result = salvage_question_coverage(
        payload,
        fusion.model_copy(update={"evidence": (cited,)}),
        user_query="Which responsibilities belong to each role?",
    )
    assert result.paragraphs == payload.paragraphs
    assert result.answer_text == payload.answer_text
    assert result.status == "partial"


def test_explicit_category_request_can_use_matching_fitted_table_header() -> None:
    """A broad cited introduction does not hide the requested category matrix."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    fusion = FusionResult.model_validate(state["fusion"])
    source = verifier_passage(
        503,
        text="| Attack type | Description |\n| --- | --- |\n| Synthetic category | Synthetic description |",
    )
    fusion = fusion.model_copy(update={"evidence": (*fusion.evidence, source)})
    result = salvage_question_coverage(
        payload, fusion, user_query="اشرح التهديدات الأمنية مع المصادر."
    )
    assert "Synthetic category" in result.answer_text
    assert any(c.chunk_id == source.chunk_id for c in result.citations)
    assert all(p in result.paragraphs for p in payload.paragraphs)


def test_unrequested_category_table_is_not_attached() -> None:
    """An uncited table header alone is insufficient without the matching ask."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    fusion = FusionResult.model_validate(state["fusion"])
    source = verifier_passage(
        504,
        text="| Attack type | Description |\n| --- | --- |\n| Synthetic category | Synthetic description |",
    )
    result = salvage_question_coverage(
        payload,
        fusion.model_copy(update={"evidence": (*fusion.evidence, source)}),
        user_query="Which responsibilities belong to each role?",
    )
    assert "Synthetic category" not in result.answer_text


def test_category_matrix_reserves_prose_slots_without_raising_caps() -> None:
    """A broad classification request cannot fill all slots before its matrix."""
    records = (
        "| Attack type | Description |\n| --- | --- |\n| Synthetic | Description |"
    )
    assert narrative_claim_limit("اشرح التهديدات الأمنية.", records) == 3
    assert narrative_claim_limit("Explain threats.", "No matrix is fitted.") == 6
    assert narrative_claim_limit("Explain responsibilities.", records) == 6
