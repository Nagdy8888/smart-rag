"""A comparison draft cannot silently omit a source-supported second subject."""

from smart_rag_core.query_answer.comparison_coverage import fill_comparison_coverage
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult

from tests.support.answer_verifier import verified_answer_state, verifier_passage


def test_missing_side_is_exact_source_owned_and_idempotent() -> None:
    """Repair the actual one-sided draft without adding invented explanatory prose."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"])
    payload = payload.model_copy(
        update={"answer_text": "Knowledge provides external factual information."}
    )
    source = verifier_passage(
        701,
        text=(
            "An agent uses knowledge and memory to enrich its context. "
            "Memory captures the agent's own history: prior user exchanges, tool outputs, and state updates. "
            "It maintains continuity between sessions."
        ),
    )
    fusion = FusionResult.model_validate(state["fusion"]).model_copy(
        update={"evidence": (source,)}
    )
    query = "Explain the difference between an agent's knowledge and memory."
    result = fill_comparison_coverage(payload, fusion, user_query=query)
    assert "Memory captures the agent's own history" in result.answer_text
    assert all(p in result.paragraphs for p in payload.paragraphs)
    assert result.citations[-1].chunk_id == source.chunk_id
    span = result.citations[-1].span
    assert span is not None and span in source.citation_text
    assert fill_comparison_coverage(result, fusion, user_query=query) == result


def test_no_missing_source_side_means_no_fabrication() -> None:
    """The coverage helper cannot invent a definition or revive a refused answer."""
    state = verified_answer_state()
    payload = AnswerPayload.model_validate(state["answer"]).model_copy(
        update={"answer_text": "Knowledge provides external factual information."}
    )
    fusion = FusionResult.model_validate(state["fusion"])
    query = "Explain the difference between knowledge and memory."
    assert fill_comparison_coverage(payload, fusion, user_query=query) == payload
    refused = AnswerPayload(
        answer_text="Insufficient authorized evidence.", status="refused"
    )
    assert fill_comparison_coverage(refused, fusion, user_query=query) == refused
