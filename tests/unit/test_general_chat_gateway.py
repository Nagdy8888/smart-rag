"""General-chat gateway: mock safety, no retrieval, and version gates."""

from __future__ import annotations

import asyncio
import inspect
import socket

import pytest
from smart_rag_core.gateways.model import (
    GeneralChatModelRequest,
    create_model_gateway,
)
from smart_rag_core.gateways.openai_general_chat import execute_openai_general_chat
from smart_rag_core.query_answer.versions import (
    ANSWER_MODEL_ID,
    GENERAL_CHAT_PROMPT_SHA256,
    GENERAL_CHAT_PROMPT_VERSION,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.settings import AgentSettings


def test_mock_general_chat_uses_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock general chat does not resolve DNS and never retrieves."""

    def _deny(*_args: object, **_kwargs: object) -> None:
        """Fail if mock generation attempts DNS.

        Args:
            *_args: Unexpected positional arguments.
            **_kwargs: Unexpected keyword arguments.
        """

        raise AssertionError("mock general chat attempted network resolution")

    monkeypatch.setattr(socket, "getaddrinfo", _deny)
    gateway = create_model_gateway(AgentSettings())
    response = asyncio.run(
        gateway.generate_general_chat(
            GeneralChatModelRequest(
                query="What is the capital of France?",
                knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
                prompt_text="general chat",
                remaining_deadline_seconds=5.0,
            )
        )
    )
    assert response.mode == "mock"
    assert response.model_calls == 1
    assert response.retrieval_performed is False
    assert response.payload["status"] == "complete"
    assert "Paris" in str(response.payload["answer_text"])
    assert "citation" not in str(response.payload).casefold()


def test_mock_general_chat_rejects_version_mismatch() -> None:
    """A wrong prompt hash fails closed before any fixture text is returned."""

    gateway = create_model_gateway(AgentSettings())
    with pytest.raises(ValueError, match="general_chat_prompt_version_mismatch"):
        asyncio.run(
            gateway.generate_general_chat(
                GeneralChatModelRequest(
                    query="Hello there",
                    knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
                    prompt_text="general chat",
                    prompt_version=GENERAL_CHAT_PROMPT_VERSION,
                    prompt_sha256="0" * 64,
                    remaining_deadline_seconds=5.0,
                )
            )
        )


def test_live_general_chat_adapter_keeps_store_false() -> None:
    """The live adapter pins store=False and the existing answer model id."""

    source = inspect.getsource(inspect.unwrap(execute_openai_general_chat))
    assert inspect.unwrap(execute_openai_general_chat) is not execute_openai_general_chat
    assert "store=False" in source
    assert "max_retries=0" in source
    assert "ALLOWED_ANSWER_MODEL_IDS" in source
    assert "GENERAL_CHAT_PROMPT_VERSION" in source
    assert "GENERAL_CHAT_PROMPT_SHA256" in source
    assert "source_records" not in source
    assert ANSWER_MODEL_ID == "gpt-4o-mini"
    assert GENERAL_CHAT_PROMPT_VERSION == "general_chat_v1"
    assert len(GENERAL_CHAT_PROMPT_SHA256) == 64
