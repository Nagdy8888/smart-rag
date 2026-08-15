"""Model and embedding gateway boundaries with deterministic mock behavior."""

from __future__ import annotations

import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal, Protocol
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.gateways.openai_rerank import (
    execute_openai_rerank,
)
from smart_rag_core.observability.langsmith_tracing import (
    configure_langsmith,
    model_call_traceable,
)
from smart_rag_core.query_profile.models import ModelInferredProfile
from smart_rag_core.query_profile.versions import (
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.retrieval.profiles import RERANK_MODEL_ID
from smart_rag_core.retrieval.rerank import rerank_input_hash
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)
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


class QueryProfileModelRequest(BaseModel):
    """Bounded structured profile request. No tools or retrieval.

    Attributes:
        operation: Must be ``query_profile``.
        query: Original user query.
        prompt_version: Pinned profile prompt version.
        prompt_sha256: Hash of that prompt file.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["query_profile"] = "query_profile"
    query: str = Field(min_length=1, max_length=2000)
    prompt_version: str = PROFILE_PROMPT_VERSION
    prompt_sha256: str = PROFILE_PROMPT_SHA256


class QueryProfileModelResponse(BaseModel):
    """Mock structured profile payload. Inferred fields stay empty.

    Attributes:
        mode: Adapter mode.
        inferred: Empty inferred object in mock mode.
        fixture_provenance: Fixture URI.
        retrieval_performed: Always false.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock"]
    inferred: ModelInferredProfile
    fixture_provenance: str = Field(max_length=256)
    retrieval_performed: Literal[False] = False


class RerankModelRequest(BaseModel):
    """Bounded structured rerank request. No tools or retrieval.

    Attributes:
        operation: Must be ``rerank``.
        query: Original user query.
        prompt_version: Pinned rerank prompt version.
        prompt_sha256: Hash of that prompt file.
        prompt_text: Prompt body used as Responses instructions.
        model_id: Allow-listed model.
        candidate_ids: Pool IDs as strings.
        excerpts: Canonical excerpts aligned with IDs.
        remaining_deadline_seconds: Client timeout bound.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["rerank"] = "rerank"
    query: str = Field(min_length=1, max_length=2000)
    prompt_version: str = RERANK_PROMPT_VERSION
    prompt_sha256: str = RERANK_PROMPT_SHA256
    prompt_text: str = Field(min_length=1, max_length=16_384)
    model_id: str = RERANK_MODEL_ID
    candidate_ids: list[str] = Field(min_length=2, max_length=20)
    excerpts: list[str] = Field(min_length=2, max_length=20)
    remaining_deadline_seconds: float = Field(gt=0, le=25)


class RerankModelResponse(BaseModel):
    """Structured rerank payload plus usage for one operation.

    Attributes:
        mode: Adapter mode.
        payload: JSON object awaiting application set-equality checks.
        request_id: Provider or fixture id.
        input_tokens: Usage input tokens.
        output_tokens: Usage output tokens.
        model_calls: Always 1 when this response is returned.
        retrieval_performed: Always false.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock", "openai"]
    payload: dict[str, object]
    request_id: str = Field(min_length=1, max_length=128)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    model_calls: Literal[1] = 1
    retrieval_performed: Literal[False] = False


class LightRagLlmRequest(BaseModel):
    """Bounded LightRAG callback request. Never a user-facing answer.

    Attributes:
        operation: Must be ``lightrag_llm``.
        role: Vendor callback role. ``extract`` is entity extraction,
            ``keyword`` is query keyword extraction, ``query`` is answer
            generation, ``vlm`` is multimodal, and ``other`` is unclassified.
        prompt: User/task prompt text from LightRAG.
        system_prompt: Optional system prompt. Empty when unused.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["lightrag_llm"] = "lightrag_llm"
    role: Literal["extract", "keyword", "query", "vlm", "other"]
    prompt: str = Field(default="", max_length=65_536)
    system_prompt: str = Field(default="", max_length=65_536)


class LightRagLlmResponse(BaseModel):
    """Mock LightRAG callback payload. Never a company-knowledge answer.

    Attributes:
        mode: Adapter mode. Qualification uses ``mock`` only.
        content: Bounded synthetic callback text.
        fixture_provenance: Fixture URI.
        retrieval_performed: Always false.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock"]
    content: str = Field(max_length=8_192)
    fixture_provenance: str = Field(max_length=256)
    retrieval_performed: Literal[False] = False


def _mock_lightrag_llm_content(role: str) -> str:
    """Return bounded synthetic LightRAG callback text for one role.

    Args:
        role: LightRAG callback role name.

    Returns:
        Vendor-format extraction rows for ``extract``, empty keyword JSON for
        ``keyword``, and an explicit non-answer for ``query`` and other roles.
    """

    if role == "extract":
        delimiter = "<|#|>"
        complete = "<|COMPLETE|>"
        return (
            f"entity{delimiter}Alpha Probe{delimiter}Concept{delimiter}"
            "Synthetic qualification entity used only in tests\n"
            f"entity{delimiter}Beta Probe{delimiter}Concept{delimiter}"
            "Second synthetic qualification entity used only in tests\n"
            f"relation{delimiter}Alpha Probe{delimiter}Beta Probe{delimiter}"
            f"links,qualification{delimiter}"
            "Alpha Probe relates to Beta Probe in synthetic qualification text\n"
            f"{complete}"
        )
    if role == "keyword":
        return '{"high_level_keywords": [], "low_level_keywords": []}'
    return "Frozen LightRAG fixture only; no answer generation was performed."


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

    async def generate_query_profile(
        self, request: QueryProfileModelRequest
    ) -> QueryProfileModelResponse:
        """Generate at most one structured profile payload.

        Args:
            request: Validated profile request.

        Returns:
            Structured profile response.
        """

        ...

    async def generate_rerank(self, request: RerankModelRequest) -> RerankModelResponse:
        """Generate at most one structured rerank payload.

        Args:
            request: Validated rerank request.

        Returns:
            Structured rerank response.
        """

        ...

    async def generate_lightrag_llm(
        self, request: LightRagLlmRequest
    ) -> LightRagLlmResponse:
        """Generate at most one LightRAG callback payload.

        Args:
            request: Validated LightRAG callback request.

        Returns:
            Bounded synthetic or unavailable response.

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

    async def generate_query_profile(
        self, request: QueryProfileModelRequest
    ) -> QueryProfileModelResponse:
        """Return an empty inferred profile without a provider call.

        Args:
            request: Structured profile request.

        Returns:
            Mock payload with empty inferred fields.

        Raises:
            ValueError: If the query exceeds the input bound or the prompt
                hash does not match the pinned prompt.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if len(request.query) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        if (
            request.prompt_version != PROFILE_PROMPT_VERSION
            or request.prompt_sha256 != PROFILE_PROMPT_SHA256
        ):
            raise ValueError("profile_prompt_version_mismatch")
        return QueryProfileModelResponse(
            mode="mock",
            inferred=ModelInferredProfile(),
            fixture_provenance=f"fixture://smart-rag/mock-model/{self._fixture_id}",
            retrieval_performed=False,
        )

    async def generate_rerank(self, request: RerankModelRequest) -> RerankModelResponse:
        """Return identity rankings without a provider call.

        Args:
            request: Structured rerank request.

        Returns:
            Mock payload that preserves fused order.

        Raises:
            ValueError: If versions, lengths, or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != RERANK_PROMPT_VERSION
            or request.prompt_sha256 != RERANK_PROMPT_SHA256
        ):
            raise ValueError("rerank_prompt_version_mismatch")
        if len(request.candidate_ids) != len(request.excerpts):
            raise ValueError("rerank_excerpt_alignment")
        joined = request.query + "".join(request.excerpts)
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        digest = rerank_input_hash(
            query=request.query,
            candidate_ids=tuple(request.candidate_ids),
            excerpts=tuple(request.excerpts),
            prompt_sha256=request.prompt_sha256,
        )
        rankings: list[dict[str, object]] = [
            {
                "chunk_id": chunk_id,
                "rank": index,
                "support": 1.0 if index == 1 else 0.5,
            }
            for index, chunk_id in enumerate(request.candidate_ids, start=1)
        ]
        return RerankModelResponse(
            mode="mock",
            payload={
                "status": "complete",
                "input_hash": digest,
                "rankings": rankings,
            },
            request_id=f"mock-rerank-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_lightrag_llm(
        self, request: LightRagLlmRequest
    ) -> LightRagLlmResponse:
        """Return a bounded synthetic LightRAG callback without a network call.

        Args:
            request: LightRAG callback request.

        Returns:
            Role-specific mock payload. ``extract`` returns the vendor tuple
            format. ``keyword`` returns empty keyword JSON. ``query`` refuses
            to answer. No retrieval is performed.

        Raises:
            ValueError: If combined prompt text exceeds the input bound.

        Side Effects:
            None. No network, provider, or retrieval calls occur.
        """

        combined = request.system_prompt + request.prompt
        if len(combined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        return LightRagLlmResponse(
            mode="mock",
            content=_mock_lightrag_llm_content(request.role),
            fixture_provenance=(
                f"fixture://smart-rag/mock-lightrag-llm/{self._fixture_id}"
            ),
            retrieval_performed=False,
        )


class OpenAIRerankAdapter:
    """Packet 5 OpenAI adapter. Chat and profile calls stay unavailable."""

    def __init__(self, *, api_key: str, max_input_chars: int) -> None:
        """Store the credential for one-shot rerank calls.

        Args:
            api_key: Provider secret. Never logged.
            max_input_chars: Deployable input bound.
        """

        self._api_key = api_key
        self._max_input_chars = max_input_chars

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Refuse chat generation. Answer prompts are Phase 6.

        Args:
            request: Foundation probe request.

        Raises:
            ModelGatewayUnavailableError: Always.
        """

        raise ModelGatewayUnavailableError("chat_generation_not_configured")

    async def generate_query_profile(
        self, request: QueryProfileModelRequest
    ) -> QueryProfileModelResponse:
        """Refuse live profile calls in this packet.

        Args:
            request: Profile request.

        Raises:
            ModelGatewayUnavailableError: Always. Packet 3 remains mock-first.
        """

        raise ModelGatewayUnavailableError("query_profile_openai_not_configured")

    async def generate_rerank(self, request: RerankModelRequest) -> RerankModelResponse:
        """Execute one Responses rerank operation.

        Args:
            request: Bounded rerank request.

        Returns:
            Provider JSON payload plus usage.

        Raises:
            OpenAIRerankError: Typed provider failure.
            ValueError: Input bound or alignment errors.

        Side Effects:
            One HTTPS call with ``max_retries=0``.
        """

        if len(request.candidate_ids) != len(request.excerpts):
            raise ValueError("rerank_excerpt_alignment")
        joined = request.query + "".join(request.excerpts)
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        digest = rerank_input_hash(
            query=request.query,
            candidate_ids=tuple(request.candidate_ids),
            excerpts=tuple(request.excerpts),
            prompt_sha256=request.prompt_sha256,
        )
        payload, request_id, input_tokens, output_tokens = execute_openai_rerank(
            api_key=self._api_key,
            prompt_text=request.prompt_text,
            prompt_sha256=request.prompt_sha256,
            prompt_version=request.prompt_version,
            model_id=request.model_id,
            query=request.query,
            candidate_ids=tuple(request.candidate_ids),
            excerpts=tuple(request.excerpts),
            input_hash=digest,
            timeout_seconds=request.remaining_deadline_seconds,
        )
        return RerankModelResponse(
            mode="openai",
            payload=payload,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_lightrag_llm(
        self, request: LightRagLlmRequest
    ) -> LightRagLlmResponse:
        """Refuse live LightRAG callbacks. Qualification uses mock mode.

        Args:
            request: LightRAG callback request.

        Raises:
            ModelGatewayUnavailableError: Always. Packet 1 never calls OpenAI.
        """

        raise ModelGatewayUnavailableError("lightrag_llm_openai_not_configured")


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
        Mock adapter when ``MOCK_MODEL_MODE`` is true; otherwise the Packet 5
        OpenAI rerank adapter (chat/profile remain unavailable).

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
