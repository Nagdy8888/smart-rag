"""Unit tests for the deterministic mock-model gateway boundary."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import textwrap

import pytest
from pydantic import ValidationError
from smart_rag_core.gateways import (
    MockModelNetworkDeniedError,
    ModelRequest,
    block_openai_network,
    create_model_gateway,
    model_types,
)
from smart_rag_core.gateways import model as model_facade
from smart_rag_core.settings import AgentSettings

_REQUEST_MODELS = (
    "AnswerModelRequest",
    "EvalJudgeModelRequest",
    "GeneralChatModelRequest",
    "LightRagLlmRequest",
    "ModelRequest",
    "QueryProfileModelRequest",
    "RerankModelRequest",
    "VerifierModelRequest",
)
_RESPONSE_MODELS = (
    "AnswerModelResponse",
    "EvalJudgeModelResponse",
    "GeneralChatModelResponse",
    "LightRagLlmResponse",
    "ModelResponse",
    "QueryProfileModelResponse",
    "RerankModelResponse",
    "VerifierModelResponse",
)


def test_mock_gateway_is_deterministic_bounded_and_provenance_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock responses are fixed, bounded, non-retrieval fixtures with no sockets."""

    settings = AgentSettings()
    gateway = create_model_gateway(settings)

    def fail_if_resolved(*args: object, **kwargs: object) -> None:
        """Fail if mock generation attempts any DNS resolution.

        Args:
            *args: Unexpected resolver positional arguments.
            **kwargs: Unexpected resolver keyword arguments.
        """

        raise AssertionError("mock generation attempted network resolution")

    monkeypatch.setattr(socket, "getaddrinfo", fail_if_resolved)
    request = ModelRequest(prompt="foundation probe")
    first = asyncio.run(gateway.generate(request))
    second = asyncio.run(gateway.generate(request))

    assert first == second
    assert first.mode == "mock"
    assert first.fixture_provenance == (
        "fixture://smart-rag/mock-model/phase-1-foundation-v1"
    )
    assert first.retrieval_performed is False
    assert "no retrieval" in first.content.lower()
    assert len(first.content) <= 512


def test_mock_gateway_rejects_deployable_input_overflow() -> None:
    """The adapter rejects requests above the settings-controlled input bound."""

    settings = AgentSettings(model_input_max_chars=4)
    gateway = create_model_gateway(settings)

    with pytest.raises(ValueError, match="4-character bound"):
        asyncio.run(gateway.generate(ModelRequest(prompt="12345")))


def test_mock_mode_denies_openai_dns_resolution() -> None:
    """The lifecycle guard makes the OpenAI API hostname unreachable."""

    async def exercise_guard() -> None:
        """Resolve the provider endpoint while the mock guard is active."""

        async with block_openai_network(enabled=True):
            with pytest.raises(MockModelNetworkDeniedError):
                socket.getaddrinfo("api.openai.com", 443)

    asyncio.run(exercise_guard())


def test_request_response_models_are_facade_aliases() -> None:
    """Moved contracts stay the same objects through the model facade."""

    for name in (*_REQUEST_MODELS, *_RESPONSE_MODELS):
        assert getattr(model_facade, name) is getattr(model_types, name)


def test_request_models_keep_frozen_schema_and_drop_unknown_fields() -> None:
    """Request models stay frozen and do not persist undeclared properties."""

    request = ModelRequest.model_validate({"prompt": "foundation probe", "tools": []})
    assert request.model_config.get("frozen") is True
    dumped = request.model_dump()
    assert dumped["operation"] == "foundation_probe"
    assert dumped["prompt"] == "foundation probe"
    assert "tools" not in dumped
    profile = model_types.QueryProfileModelRequest.model_validate(
        {"query": "Hello", "knowledge_scope": "general_knowledge"}
    )
    assert set(model_types.QueryProfileModelRequest.model_fields) == {
        "operation",
        "query",
        "prompt_version",
        "prompt_sha256",
        "prompt_text",
        "model_id",
        "remaining_deadline_seconds",
        "recent_memory",
    }
    assert "knowledge_scope" not in profile.model_dump()
    with pytest.raises(ValidationError):
        ModelRequest.model_validate({"prompt": ""})


def test_gateways_package_import_is_socket_free_and_lazy() -> None:
    """Importing ``smart_rag_core.gateways`` must not load the model facade."""

    probe = textwrap.dedent(
        """
        import socket
        import sys
        import types

        class Trap:
            def __init__(self, *args, **kwargs):
                raise AssertionError("provider client constructed during import")

        def denied_socket(*args, **kwargs):
            raise AssertionError("socket constructed during import")

        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = Trap
        fake_openai.AsyncOpenAI = Trap
        fake_openai.APIStatusError = Exception
        fake_openai.APITimeoutError = Exception
        fake_openai.AuthenticationError = Exception
        sys.modules["openai"] = fake_openai
        socket.create_connection = denied_socket
        socket.getaddrinfo = denied_socket

        import smart_rag_core.gateways as gateways

        assert "smart_rag_core.gateways.model" not in sys.modules
        assert "smart_rag_core.gateways.model_gateway" not in sys.modules
        assert gateways.EmbeddingGateway is not None
        """
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and probe
        (sys.executable, "-c", probe),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
