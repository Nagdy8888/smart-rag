"""Application-owned model gateway, factory, and mock-mode network denial."""

from __future__ import annotations

import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import patch

from smart_rag_core.gateways.mock_model import MockModelAdapter
from smart_rag_core.gateways.model_protocol import ModelAdapter
from smart_rag_core.gateways.model_types import (
    OPENAI_API_HOST,
    AnswerModelRequest,
    AnswerModelResponse,
    ConversationTitleModelRequest,
    ConversationTitleModelResponse,
    EvalJudgeModelRequest,
    EvalJudgeModelResponse,
    GeneralChatModelRequest,
    GeneralChatModelResponse,
    LightRagLlmRequest,
    LightRagLlmResponse,
    MockModelNetworkDeniedError,
    ModelGatewayUnavailableError,
    ModelRequest,
    ModelResponse,
    QueryProfileModelRequest,
    QueryProfileModelResponse,
    RerankModelRequest,
    RerankModelResponse,
    VerifierModelRequest,
    VerifierModelResponse,
    WebAnswerModelRequest,
    WebAnswerModelResponse,
)
from smart_rag_core.gateways.openai_adapter import OpenAIRerankAdapter
from smart_rag_core.observability.langsmith_tracing import (
    configure_langsmith,
    model_call_traceable,
)
from smart_rag_core.settings import SharedSettings


class ModelGateway:
    """Single application-owned boundary for all model invocations."""

    def __init__(self, adapter: ModelAdapter) -> None:
        """Initialize the gateway with one lifecycle-created adapter.

        Args:
            adapter: Provider or frozen-fixture adapter.
        """

        self._adapter = adapter

    @model_call_traceable(name="model.generate")
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

    @model_call_traceable(name="model.query_profile")
    async def generate_query_profile(
        self, request: QueryProfileModelRequest
    ) -> QueryProfileModelResponse:
        """Delegate one structured profile request. Never a second hidden call.

        Args:
            request: Bounded profile request.

        Returns:
            Structured profile response.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_query_profile(request)

    @model_call_traceable(name="model.rerank")
    async def generate_rerank(self, request: RerankModelRequest) -> RerankModelResponse:
        """Delegate one structured rerank request. Never a hidden retry.

        Args:
            request: Bounded rerank request.

        Returns:
            Structured rerank response plus usage.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            OpenAIRerankError: Typed provider failure.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_rerank(request)

    @model_call_traceable(name="model.answer")
    async def generate_answer(self, request: AnswerModelRequest) -> AnswerModelResponse:
        """Delegate one structured answer request. Never a hidden retry.

        Args:
            request: Bounded answer request.

        Returns:
            Structured answer response plus usage.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_answer(request)

    @model_call_traceable(name="model.general_chat")
    async def generate_general_chat(
        self, request: GeneralChatModelRequest
    ) -> GeneralChatModelResponse:
        """Delegate one no-source general-chat request. Never a hidden retry.

        Args:
            request: Bounded general-chat request.

        Returns:
            Structured general-chat response plus usage.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_general_chat(request)

    @model_call_traceable(name="model.web_answer")
    async def generate_web_answer(
        self, request: WebAnswerModelRequest
    ) -> WebAnswerModelResponse:
        """Delegate one Web-research synthesis request. Never a hidden retry.

        Args:
            request: Bounded Web-answer request.

        Returns:
            Structured Web-answer response plus usage.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_web_answer(request)

    @model_call_traceable(name="model.conversation_title")
    async def generate_conversation_title(
        self, request: ConversationTitleModelRequest
    ) -> ConversationTitleModelResponse:
        """Delegate one session-title request. Never a hidden retry.

        Args:
            request: Bounded title request.

        Returns:
            Structured title response plus usage.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_conversation_title(request)

    @model_call_traceable(name="model.verifier")
    async def generate_verifier(
        self, request: VerifierModelRequest
    ) -> VerifierModelResponse:
        """Delegate one structured verifier request. Never a second batch.

        Args:
            request: Bounded verifier request.

        Returns:
            Structured verifier response plus usage.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_verifier(request)

    @model_call_traceable(name="model.eval_judge")
    async def generate_eval_judge(
        self, request: EvalJudgeModelRequest
    ) -> EvalJudgeModelResponse:
        """Delegate one structured eval-judge request. Never a hidden retry.

        Args:
            request: Bounded judge request.

        Returns:
            Structured judge response plus usage.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.
        """

        return await self._adapter.generate_eval_judge(request)

    @model_call_traceable(name="model.lightrag_llm")
    async def generate_lightrag_llm(
        self, request: LightRagLlmRequest
    ) -> LightRagLlmResponse:
        """Delegate one LightRAG callback to the configured adapter.

        Args:
            request: Bounded LightRAG callback request.

        Returns:
            Provenance-marked callback payload.

        Raises:
            ModelGatewayUnavailableError: If the adapter is unavailable.
            ValueError: If a deployable bound is exceeded.

        Side Effects:
            Creates a LangSmith span when tracing is enabled. Exported fields
            are role and counts, never prompt text.
        """

        return await self._adapter.generate_lightrag_llm(request)


def create_model_gateway(settings: SharedSettings) -> ModelGateway:
    """Create the lifecycle-scoped gateway selected by validated settings.

    Args:
        settings: Validated deployable settings.

    Returns:
        Mock adapter when ``MOCK_MODEL_MODE`` is true; otherwise the live
        OpenAI adapter (chat/profile remain unavailable; LightRAG extract
        uses Responses).

    Raises:
        ModelGatewayUnavailableError: If real mode has no API key.

    Side Effects:
        Configures LangSmith hide/tracing flags from ``settings``.
    """

    configure_langsmith(settings)
    if settings.mock_model_mode:
        return ModelGateway(
            MockModelAdapter(
                fixture_id=settings.mock_fixture_id,
                max_input_chars=settings.model_input_max_chars,
            )
        )
    secret = settings.openai_api_key
    if secret is None:
        raise ModelGatewayUnavailableError(
            "OPENAI_API_KEY is required outside mock mode"
        )
    return ModelGateway(
        OpenAIRerankAdapter(
            api_key=secret.get_secret_value(),
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
