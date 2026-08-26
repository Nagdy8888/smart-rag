"""Unit tests for the local LangGraph Studio query adapter."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from smart_rag_agents.query.state import pending_query_state
from smart_rag_agents.query.studio import (
    query_text_from_studio_input,
    seed_studio_runtime,
    studio_authorized_runtime,
    studio_response_text,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily


def test_query_text_prefers_user_query_over_messages() -> None:
    """Explicit ``user_query`` wins over Studio chat messages."""

    assert (
        query_text_from_studio_input(
            {
                "user_query": " invoice status ",
                "messages": [{"role": "human", "content": "ignored"}],
            }
        )
        == "invoice status"
    )


def test_query_text_reads_last_human_message() -> None:
    """Studio chat input can populate the query when ``user_query`` is absent."""

    assert (
        query_text_from_studio_input(
            {
                "messages": [
                    {"role": "human", "content": "first"},
                    {"role": "ai", "content": "ack"},
                    {"type": "human", "content": [{"text": "second"}]},
                ]
            }
        )
        == "second"
    )


def test_query_text_reads_langchain_human_message() -> None:
    """Studio's message reducer may convert chat input to message objects."""

    assert (
        query_text_from_studio_input(
            {
                "messages": [
                    HumanMessage(content="What is the invoice status?"),
                ]
            }
        )
        == "What is the invoice status?"
    )


def test_studio_runtime_uses_envelope_ceilings_and_local_status() -> None:
    """Synthetic context copies Hybrid ceilings and is labeled studio_local."""

    context = studio_authorized_runtime(
        query="status?",
        family=Phase6RouteFamily.HYBRID,
        thread_id="thread-a",
    )
    assert context.status == "studio_local"
    assert context.route_family is Phase6RouteFamily.HYBRID
    assert context.model_call_ceiling == 7
    assert context.recursion_limit == 24
    assert len(context.payload_hash) == 64
    again = studio_authorized_runtime(
        query="status?",
        family=Phase6RouteFamily.HYBRID,
        thread_id="thread-a",
    )
    assert again.conversation_id == context.conversation_id
    assert again.user_id == context.user_id
    assert again.run_id != context.run_id


def test_seed_studio_runtime_rejects_unknown_family_without_context() -> None:
    """Unknown Studio families fail closed and do not mint authorized_runtime."""

    seeded = seed_studio_runtime(
        {
            **pending_query_state(user_query="hello"),
            "route_family": "not-a-family",
            "messages": [],
        },
        {"configurable": {"thread_id": str(uuid4())}},
    )
    assert seeded["status"] == "admission_rejected"
    assert seeded["authorized_runtime"] is None
    assert "allow-listed" in seeded["detail"]


def test_apply_studio_langsmith_flags_without_key_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Studio flag apply stays off when tracing is disabled."""

    from smart_rag_agents.query.studio_tracing import apply_studio_langsmith_flags

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    applied = apply_studio_langsmith_flags()
    assert applied["LANGSMITH_TRACING"] == "false"


def test_apply_studio_langsmith_flags_enables_langchain_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A present Studio key enables redacted LangGraph export."""

    from smart_rag_agents.query.studio_tracing import apply_studio_langsmith_flags

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_canary_must_not_leak")
    monkeypatch.setenv("LANGSMITH_PROJECT", "smart-rag")
    applied = apply_studio_langsmith_flags()
    assert applied["LANGSMITH_TRACING"] == "true"
    assert applied["LANGCHAIN_TRACING_V2"] == "true"
    assert "lsv2_canary" not in repr(applied)


def test_studio_response_appends_token_usage() -> None:
    """Studio Chat shows provider tokens under the answer when a model ran."""

    from smart_rag_core.query_answer.models import AnswerPayload

    state = pending_query_state(user_query="hello")
    state["answer"] = AnswerPayload(
        answer_text="Hello from Studio.",
        status="complete",
    ).model_dump(mode="json")
    state["prompt_tokens"] = 12
    state["completion_tokens"] = 7
    text = studio_response_text(state)
    assert text.startswith("Hello from Studio.")
    assert "12 prompt · 7 completion" in text
    unused = pending_query_state(user_query="hello")
    unused["answer"] = AnswerPayload(
        answer_text="Hello from Studio.",
        status="complete",
    ).model_dump(mode="json")
    assert studio_response_text(unused) == "Hello from Studio."
