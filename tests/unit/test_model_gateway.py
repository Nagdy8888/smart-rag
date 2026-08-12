"""Unit tests for the deterministic mock-model gateway boundary."""

from __future__ import annotations

import asyncio
import socket

import pytest
from smart_rag_core.gateways import (
    MockModelNetworkDeniedError,
    ModelRequest,
    block_openai_network,
    create_model_gateway,
)
from smart_rag_core.settings import AgentSettings


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
