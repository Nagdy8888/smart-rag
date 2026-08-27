"""Session-title sanitization, skip rules, and prompt pin."""

from __future__ import annotations

from smart_rag_core.conversations.title import (
    CONVERSATION_TITLE_MAX,
    compact_conversation_title,
    conversation_title_json_schema,
    mock_conversation_title_payload,
    needs_llm_conversation_title,
    title_generation_excerpt,
)
from smart_rag_core.query_answer.versions import (
    CONVERSATION_TITLE_PROMPT_SHA256,
    CONVERSATION_TITLE_PROMPT_VERSION,
)

from tests.support.answer_verifier import verifier_prompt_digest


def test_conversation_title_prompt_hash_matches_file() -> None:
    """Pinned title prompt digest matches the LF-normalized markdown file."""

    assert CONVERSATION_TITLE_PROMPT_VERSION == "conversation_title_v1"
    assert CONVERSATION_TITLE_PROMPT_SHA256 == verifier_prompt_digest(
        "conversation_title_v1.md"
    )


def test_compact_conversation_title_bounds_and_fallback() -> None:
    """Empty input becomes Chat; long input is clipped at 80."""

    assert compact_conversation_title("  \n ") == "Chat"
    assert compact_conversation_title('"Vacation policy"') == "Vacation policy"
    long = "A" * (CONVERSATION_TITLE_MAX + 12)
    title = compact_conversation_title(long)
    assert title.endswith("…")
    assert len(title) == CONVERSATION_TITLE_MAX


def test_title_generation_excerpt_uses_stored_prompt_before_persist() -> None:
    """Empty message rows still feed the create-time prompt to the title model."""

    assert (
        title_generation_excerpt("hello from the other side", "")
        == "hello from the other side"
    )
    assert title_generation_excerpt("Chat", "") == ""
    assert title_generation_excerpt(None, "  What is PTO?  ") == "What is PTO?"


def test_needs_llm_title_only_for_fallback() -> None:
    """LLM refresh runs only while the title is still the first prompt."""

    assert needs_llm_conversation_title(None, "Summarize the policy") is True
    assert needs_llm_conversation_title("Chat", "Summarize the policy") is True
    assert (
        needs_llm_conversation_title("Summarize the policy", "Summarize the policy")
        is True
    )
    assert (
        needs_llm_conversation_title("Vacation policy", "Summarize the policy") is False
    )


def test_title_schema_and_mock_payload_are_title_only() -> None:
    """Structured output and mock fixture expose title only."""

    schema = conversation_title_json_schema()
    assert schema["required"] == ["title"]
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert "answer_text" not in properties
    payload = mock_conversation_title_payload("  What is PTO?\n")
    assert payload == {"title": "What is PTO?"}
