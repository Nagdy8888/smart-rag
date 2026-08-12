"""Model gateway boundary with deterministic, network-denied mock behavior."""

from __future__ import annotations

import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal, Protocol
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.settings import SharedSettings

OPENAI_API_HOST = "api.openai.com"


class ModelGatewayUnavailableError(RuntimeError):
    """Report that the real provider adapter is not configured in Phase 1."""


class MockModelNetworkDeniedError(OSError):
    """Report an OpenAI network attempt while mock mode is active."""


class ModelRequest(BaseModel):
    """Bounded input accepted by the shared model gateway.

    Attributes:
        operation: Foundation-only operation identifier. Retrieval and answer
            operations are intentionally absent.
        prompt: Bounded probe text. Mock responses never echo this content.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["foundation_probe"] = "foundation_probe"
    prompt: str = Field(min_length=1, max_length=65_536)


class ModelResponse(BaseModel):
    """Provenance-marked response returned by the model gateway.

    Attributes:
        mode: Adapter mode that produced the response.
        content: Honest foundation fixture text, never a retrieval answer.
        fixture_provenance: Stable fixture URI for auditability.
        retrieval_performed: Always false because Packet 4 implements no
            retrieval behavior.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock"]
    content: str = Field(max_length=512)
    fixture_provenance: str = Field(max_length=256)
    retrieval_performed: Literal[False] = False


class ModelAdapter(Protocol):
    """Protocol implemented by model provider adapters."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a bounded response for one validated request.

        Args:
            request: Validated gateway request.

        Returns:
            Adapter response with explicit provenance.

        Raises:
            ModelGatewayUnavailableError: If the selected adapter cannot run.
        """

        ...


class MockModelAdapter:
    """Frozen adapter that performs no provider or retrieval work."""

    def __init__(self, *, fixture_id: str, max_input_chars: int) -> None:
        """Initialize deterministic fixture metadata and input bound.

        Args:
            fixture_id: Validated frozen fixture identifier.
            max_input_chars: Maximum accepted prompt length.
        """

        self._fixture_id = fixture_id
        self._max_input_chars = max_input_chars

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Return an honest frozen fixture without opening a network socket.

        Args:
            request: Foundation probe request.

        Returns:
            Deterministic fixture response that explicitly denies retrieval.

        Raises:
            ValueError: If the request exceeds the deployable input bound.

        Side Effects:
            None. No network, provider, persistence, or retrieval calls occur.
        """

        if len(request.prompt) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        return ModelResponse(
            mode="mock",
            content=(
                "Frozen model fixture only; no retrieval, provider call, or "
                "business answer was performed."
            ),
            fixture_provenance=f"fixture://smart-rag/mock-model/{self._fixture_id}",
            retrieval_performed=False,
        )


class ModelGateway:
    """Single application-owned boundary for all model invocations."""

    def __init__(self, adapter: ModelAdapter) -> None:
        """Initialize the gateway with one lifecycle-created adapter.

        Args:
            adapter: Provider or frozen-fixture adapter.
        """

        self._adapter = adapter

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Delegate one validated request to the configured adapter.

        Args:
            request: Bounded gateway request.

        Returns:
            Provenance-marked adapter response.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate(request)


def create_model_gateway(settings: SharedSettings) -> ModelGateway:
    """Create the lifecycle-scoped gateway selected by validated settings.

    Args:
        settings: Validated deployable settings.

    Returns:
        A gateway backed by the frozen mock adapter.

    Raises:
        ModelGatewayUnavailableError: If real-model mode is selected. The
            OpenAI adapter is intentionally deferred; no fake real path exists.
    """

    if not settings.mock_model_mode:
        raise ModelGatewayUnavailableError(
            "Real OpenAI adapter is not configured in the Phase 1 foundation"
        )
    return ModelGateway(
        MockModelAdapter(
            fixture_id=settings.mock_fixture_id,
            max_input_chars=settings.model_input_max_chars,
        )
    )


@asynccontextmanager
async def block_openai_network(enabled: bool) -> AsyncGenerator[None]:
    """Deny DNS resolution for OpenAI while mock-model mode is active.

    Args:
        enabled: Whether to install the process-wide mock-mode guard.

    Yields:
        Control while the guard is active.

    Raises:
        MockModelNetworkDeniedError: If code attempts to resolve
            ``api.openai.com`` while the guard is active.

    Side Effects:
        Temporarily patches ``socket.getaddrinfo`` for the process. Other hosts
        continue through the original resolver and the patch is restored on
        context exit.
    """

    if not enabled:
        yield
        return

    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(
        host: str | bytes | None,
        port: str | int | None,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
        ]
    ]:
        """Resolve non-OpenAI hosts and deny the provider endpoint.

        Args:
            host: Hostname or address to resolve.
            port: Service name or port.
            family: Address family filter.
            type: Socket kind filter.
            proto: Protocol filter.
            flags: Resolver flags.

        Returns:
            Resolver results for allowed hosts.

        Raises:
            MockModelNetworkDeniedError: If ``host`` is the OpenAI API.
        """

        normalized_host = (
            host.decode("ascii", errors="ignore") if isinstance(host, bytes) else host
        )
        if (
            normalized_host is not None
            and normalized_host.rstrip(".").lower() == OPENAI_API_HOST
        ):
            raise MockModelNetworkDeniedError(
                "OpenAI network access is disabled by MOCK_MODEL_MODE"
            )
        return original_getaddrinfo(host, port, family, type, proto, flags)

    with patch.object(socket, "getaddrinfo", new=guarded_getaddrinfo):
        yield
