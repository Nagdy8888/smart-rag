"""A wrong prose block cannot be released as a requested original function."""

from __future__ import annotations

import pytest
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.source_syntax import missing_requested_definition


@pytest.mark.parametrize(
    "body",
    [
        "Text explaining a different source example.",
        "def other_function():\n    return 3",
        "# def choose_widget():\nprint('not the requested function')",
    ],
)
def test_unrelated_fence_fails_named_definition_identity(body: str) -> None:
    """A code fence, comment, or other function is not the requested definition."""
    payload = AnswerPayload(answer_text=f"```python\n{body}\n```", status="complete")
    assert missing_requested_definition(
        payload, user_query="Show the choose_widget function."
    )


def test_original_syntax_error_does_not_change_definition_identity() -> None:
    """Original invalid source still reaches the separate syntax-warning gate."""
    payload = AnswerPayload(
        answer_text='```python\ndef choose_widget():\n    value = "broken\n```',
        status="partial",
    )
    assert not missing_requested_definition(
        payload, user_query="Show the choose_widget function."
    )


def test_prose_query_does_not_require_python() -> None:
    """Ordinary conceptual questions keep their existing answer shape."""
    payload = AnswerPayload(answer_text="A conceptual answer.", status="complete")
    assert not missing_requested_definition(payload, user_query="What is memory?")
