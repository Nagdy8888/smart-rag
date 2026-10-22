"""Structural source repairs keep existing supported explanations and mappings."""

from smart_rag_core.query_answer.code_explanation import (
    keep_code_explanation,
    with_source_code_explanation,
)
from smart_rag_core.query_answer.format_shape import ensure_fenced_code
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)

from tests.support.answer_verifier import verifier_fusion, verifier_passage


def test_missing_explanation_copies_only_same_version_source_prose() -> None:
    """A timed-out answer can still cite the introductory paragraph without inventing prose."""
    prose = (
        "The actor generates candidate plans while the critic evaluates each plan "
        "against the stated quality rubric and requests another iteration when needed."
    )
    source = verifier_passage(
        982, text=prose + "\n\ndef construct_actor_critic_graph():\n    return graph"
    )
    code = _payload("def construct_actor_critic_graph():\n    return graph", "code")
    code = code.model_copy(
        update={
            "citations": (
                code.citations[0].model_copy(update={"chunk_id": source.chunk_id}),
            )
        }
    )
    result = with_source_code_explanation(
        code,
        verifier_fusion(source),
        query="Show construct_actor_critic_graph and explain its nodes.",
    )
    assert result.paragraphs[-1].text == prose
    assert result.citations[-1].span == prose
    assert result.citations[-1].chunk_id == source.chunk_id
    assert len(result.atomic_links) == 2
    assert (
        with_source_code_explanation(
            code,
            verifier_fusion(),
            query="Show construct_actor_critic_graph and explain it.",
        )
        is code
    )


def _payload(text: str, link_id: str) -> AnswerPayload:
    """Create one independently mapped paragraph."""
    return AnswerPayload(
        answer_text=text,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=text, link_ids=(link_id,)),
        ),
        atomic_links=(
            AtomicLink(
                link_id=link_id,
                claim=text,
                chunk_ids=("source",),
                kind="fact",
                priority=10,
            ),
        ),
        citations=(
            AnswerCitation(
                chunk_id="source",
                span="Exact source words.",
                paragraph_index=0,
                atomic_link_id=link_id,
            ),
        ),
    )


def test_fence_normalization_keeps_explanation_in_the_same_claim() -> None:
    """Finding an existing fence must retain both surrounding prose segments."""
    text = "The example follows:\n```python\ndef widget():\n    return 1\n```\nThe return value is the integer 1."
    assert ensure_fenced_code(text) == text


def test_repaired_mixed_claim_keeps_its_explanation_and_new_identity() -> None:
    """Repairing code within a mixed claim does not discard its final sentence."""
    original = _payload(
        "```python\ndef widget():\n    return wrong\n```\nThe function returns the saved result.",
        "code-def-1",
    )
    replacement = _payload("def widget():\n    return saved_result", "code-def-1")
    result = keep_code_explanation(
        original, replacement, query="Show widget and explain it."
    )
    assert result.paragraphs[1].text == "The function returns the saved result."
    assert result.paragraphs[1].link_ids == ("code-prose-1",)
    assert result.citations[1].atomic_link_id == "code-prose-1"
    assert "return wrong" not in result.answer_text


def test_code_replacement_retains_the_explanation_with_its_own_citation() -> None:
    """Both claims remain independently checkable after the code repair."""
    original = _payload(
        "**Behavior**\nThe function returns the saved result.", "explanation"
    )
    replacement = _payload("def widget():\n    return saved_result", "code-def-1")
    result = keep_code_explanation(
        original, replacement, query="Show widget and explain its behavior."
    )
    assert len(result.paragraphs) == 2
    assert result.paragraphs[1].text == original.paragraphs[0].text
    assert result.citations[1].atomic_link_id == "explanation"
    assert result.citations[1].paragraph_index == 1
    assert result.atomic_links[1].priority > result.atomic_links[0].priority


def test_exact_code_copy_request_does_not_append_prose() -> None:
    """Only explicit explanatory requests retain additional prose."""
    original = _payload("An explanation.", "explanation")
    replacement = _payload("def widget():\n    return 1", "code-def-1")
    assert (
        keep_code_explanation(original, replacement, query="Copy widget exactly.")
        is replacement
    )


def test_uncited_or_colliding_prose_cannot_be_restored() -> None:
    """Unmapped or identity-conflicting text never acquires the code citation."""
    replacement = _payload("def widget():\n    return 1", "code-def-1")
    for original in (
        _payload("Uncited prose.", "explanation").model_copy(update={"citations": ()}),
        _payload("Conflicting prose.", "code-def-1"),
    ):
        result = keep_code_explanation(original, replacement, query="Explain widget.")
        assert result.answer_text == replacement.answer_text
