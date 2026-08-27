"""Conversation-title gateway: mock safety, no retrieval, and version gates."""

from __future__ import annotations

import asyncio
import inspect
import socket

import pytest
from smart_rag_core.gateways.model import (
    ConversationTitleModelRequest,
    create_model_gateway,
)
from smart_rag_core.gateways.openai_conversation_title import (
    execute_openai_conversation_title,
)
from smart_rag_core.query_answer.versions import (
    CONVERSATION_TITLE_MODEL_ID,
    CONVERSATION_TITLE_PROMPT_SHA256,
    CONVERSATION_TITLE_PROMPT_VERSION,
)
from smart_rag_core.settings import AgentSettings


def test_mock_conversation_title_uses_no_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock title generation does not resolve DNS and never retrieves."""

    def _deny(*_args: object, **_kwargs: object) -> None:
        """Fail if mock generation attempts DNS.

        Args:
            *_args: Unexpected positional arguments.
            **_kwargs: Unexpected keyword arguments.
        """

        raise AssertionError("mock conversation title attempted network resolution")

    monkeypatch.setattr(socket, "getaddrinfo", _deny)
    gateway = create_model_gateway(AgentSettings())
    response = asyncio.run(
        gateway.generate_conversation_title(
            ConversationTitleModelRequest(
                user_excerpt="What is the vacation policy?",
                assistant_excerpt="PTO accrues monthly.",
                prompt_text="conversation title",
                remaining_deadline_seconds=5.0,
            )
        )
    )
    assert response.mode == "mock"
    assert response.model_calls == 1
    assert response.retrieval_performed is False
    assert response.payload["title"] == "What is the vacation policy?"
    assert "citation" not in str(response.payload).casefold()


def test_mock_conversation_title_rejects_version_mismatch() -> None:
    """A wrong prompt hash fails closed before any fixture text is returned."""

    gateway = create_model_gateway(AgentSettings())
    with pytest.raises(ValueError, match="conversation_title_prompt_version_mismatch"):
        asyncio.run(
            gateway.generate_conversation_title(
                ConversationTitleModelRequest(
                    user_excerpt="Hello there",
                    prompt_text="conversation title",
                    prompt_version=CONVERSATION_TITLE_PROMPT_VERSION,
                    prompt_sha256="0" * 64,
                    remaining_deadline_seconds=5.0,
                )
            )
        )


def test_live_conversation_title_adapter_keeps_store_false() -> None:
    """The live adapter pins store=False and the existing answer model id."""

    source = inspect.getsource(inspect.unwrap(execute_openai_conversation_title))
    assert (
        inspect.unwrap(execute_openai_conversation_title)
        is not execute_openai_conversation_title
    )
    assert "store=False" in source
    assert "max_retries=0" in source
    assert "ALLOWED_CONVERSATION_TITLE_MODEL_IDS" in source
    assert "CONVERSATION_TITLE_PROMPT_VERSION" in source
    assert "CONVERSATION_TITLE_PROMPT_SHA256" in source
    assert "source_records" not in source
    assert CONVERSATION_TITLE_MODEL_ID == "gpt-4o-mini"
    assert CONVERSATION_TITLE_PROMPT_VERSION == "conversation_title_v1"
    assert len(CONVERSATION_TITLE_PROMPT_SHA256) == 64
