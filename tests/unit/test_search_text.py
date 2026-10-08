"""Question-sentence search text and dense rank merge."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.retrieval.hybrid_run.assemble import query_texts
from smart_rag_core.retrieval.hybrid_run.search_text import (
    merge_variant_ranks,
    question_search_text,
)

from tests.unit.test_hybrid_run import _caller, _retriever


def test_instruction_sentences_are_not_searched() -> None:
    """Only the sentence that ends in a question mark is the search text."""

    message = (
        "In the company document Policy Handbook, what is the refund period? "
        "Use only that document."
    )
    text = question_search_text(message, ("Policy Handbook",))
    assert "Use only" not in text
    assert "Policy Handbook" not in text
    assert text.endswith("what is the refund period?")


def test_message_without_a_question_is_unchanged() -> None:
    """No question mark means the full message is the search text."""

    message = "Summarize the refund policy."
    assert question_search_text(message) == message


def test_only_authorized_selectors_are_removed() -> None:
    """A title that was not resolved stays in the question sentence."""

    message = "In the company document Secret Title, what does Acme require?"
    assert "Secret Title" not in question_search_text(message, ("Secret Title",))
    kept = question_search_text(message, ())
    assert "Secret Title" in kept


def test_first_in_either_list_outranks_deep_in_both() -> None:
    """Reciprocal rank prefers a top hit over a chunk that is deep twice."""

    top = uuid4()
    deep = uuid4()
    first = [top, *[uuid4() for _index in range(30)]]
    second = [deep, *[uuid4() for _index in range(30)], top]
    merged = merge_variant_ranks((first, second))
    assert merged.index(top) < merged.index(deep)


def test_question_sentence_still_embeds_once() -> None:
    """The original and the question share one embedding batch."""

    retriever = _retriever()
    result = retriever.retrieve(
        query="In the company document Policy, what is the refund period? Use only that document.",
        caller=_caller(),
        source_selectors=("Policy",),
        channel_jobs={"dense": lambda: ()},
    )
    assert result.embedding_call_count == 1
    texts = query_texts(
        "In the company document Policy, what is the refund period? Use only that document.",
        None,
        ("Policy",),
    )
    assert texts[0].endswith("document.")
    assert texts[1].endswith("what is the refund period?")
    assert "Use only" not in texts[1]
