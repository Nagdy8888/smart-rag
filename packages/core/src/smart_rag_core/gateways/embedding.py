"""Embedding gateway types, mock adapter, and OpenAI query-time adapter."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.observability.langsmith_tracing import (
    configure_langsmith,
    model_call_traceable,
    traced_async_openai_client,
    traced_embeddings_create_async,
)
from smart_rag_core.settings import SharedSettings

# Hybrid ingest HTTP timeout. LightRAG callbacks pass 20s instead.
# Keep equal to ``retrieval.graph.OPENAI_EMBEDDING_TIMEOUT_SECONDS``.
OPENAI_EMBEDDING_TIMEOUT_SECONDS = 120.0

# Published list price USD per 1M input tokens for text-embedding-3-large,
# same pin used by scripts/embedding_qualification_bakeoff.py (2026-08-12).
_OPENAI_LARGE_USD_PER_MILLION = Decimal("0.13")


class EmbeddingRequest(BaseModel):
    """Bounded embedding batch accepted by the shared gateway."""

    model_config = ConfigDict(frozen=True)

    operation_key: str = Field(min_length=1, max_length=256)
    inputs: tuple[str, ...] = Field(min_length=1)
    model: str = Field(min_length=1, max_length=128)
    dimensions: int = Field(ge=1, le=3072)
    timeout_seconds: float = Field(
        default=OPENAI_EMBEDDING_TIMEOUT_SECONDS, gt=0, le=600
    )


class EmbeddingResponse(BaseModel):
    """Provenance-marked embedding batch response."""

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock", "openai"]
    vectors: tuple[tuple[float, ...], ...]
    provider_request_id: str
    fixture_provenance: str
    estimated_cost_usd: Decimal = Decimal("0")


class EmbeddingAdapter(Protocol):
    """Protocol implemented by embedding provider adapters."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed one bounded batch."""

        ...


class EmbeddingProviderError(RuntimeError):
    """Typed OpenAI embedding failure. Vendor SDK retries stay at zero."""

    def __init__(self, reason: str) -> None:
        """Store a machine-readable reason.

        Args:
            reason: Short code such as ``embedding_timeout`` or
                ``embedding_rate_limited``.
        """

        super().__init__(reason)
        self.reason = reason


class MockEmbeddingAdapter:
    """Deterministic embedding adapter with no provider network access."""

    def __init__(self, *, fixture_id: str) -> None:
        """Initialize deterministic fixture metadata.

        Args:
            fixture_id: Frozen mock fixture identifier from settings.
        """

        self._fixture_id = fixture_id

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return deterministic unit vectors keyed by contextual input text.

        Args:
            request: Bounded embedding batch.

        Returns:
            Mock vectors plus zero cost. ``mode`` is always ``mock``.
        """

        vectors = tuple(
            tuple(mock_embedding_vector(text, dimensions=request.dimensions))
            for text in request.inputs
        )
        request_digest = hashlib.sha256(
            "|".join(request.inputs).encode("utf-8")
        ).hexdigest()[:16]
        return EmbeddingResponse(
            mode="mock",
            vectors=vectors,
            provider_request_id=f"mock-embed-{request_digest}",
            fixture_provenance=f"fixture://smart-rag/mock-embedding/{self._fixture_id}",
            estimated_cost_usd=Decimal("0"),
        )


class OpenAIEmbeddingAdapter:
    """Pinned OpenAI embeddings adapter. No second embeddings path exists."""

    def __init__(self, *, api_key: str) -> None:
        """Store the provider credential.

        Args:
            api_key: ``OPENAI_API_KEY`` secret. Never logged.

        Raises:
            ModelGatewayUnavailableError: If the key is missing or blank.
        """

        from smart_rag_core.gateways.model import ModelGatewayUnavailableError

        if not api_key.strip():
            raise ModelGatewayUnavailableError(
                "OPENAI_API_KEY is required outside mock mode"
            )
        self._api_key = api_key

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed one batch through the traced async OpenAI client.

        Args:
            request: Bounded embedding batch. Model and dimensions should match
                the pinned ingestion policy; response length is still checked.
                ``timeout_seconds`` is the provider HTTP bound. LightRAG
                callers must pass a value below the vendor embedding watchdog.

        Returns:
            Vectors ordered by ``data.index``, never by list order alone.

        Raises:
            ValueError: If a vector is missing, duplicated, or the wrong size.
            EmbeddingProviderError: Timeout, HTTP 429, auth, or other provider
                failures. SDK retries stay at zero.

        Side Effects:
            One HTTPS ``embeddings.create`` call via
            ``traced_embeddings_create_async``.
        """

        from openai import APIStatusError, APITimeoutError, AuthenticationError

        client = traced_async_openai_client(
            api_key=self._api_key,
            max_retries=0,
            timeout=request.timeout_seconds,
        )
        try:
            response = await traced_embeddings_create_async(
                client,
                input_usd_per_million=_OPENAI_LARGE_USD_PER_MILLION,
                model=request.model,
                input=list(request.inputs),
                dimensions=request.dimensions,
                encoding_format="float",
            )
        except APITimeoutError as error:
            raise EmbeddingProviderError("embedding_timeout") from error
        except AuthenticationError as error:
            raise EmbeddingProviderError("embedding_provider_error") from error
        except APIStatusError as error:
            if error.status_code == 429:
                raise EmbeddingProviderError("embedding_rate_limited") from error
            raise EmbeddingProviderError("embedding_provider_error") from error
        by_index: dict[int, tuple[float, ...]] = {}
        for item in response.data:
            index = int(item.index)
            if index in by_index:
                raise ValueError("embedding_index_mismatch")
            by_index[index] = tuple(float(value) for value in item.embedding)
        expected = set(range(len(request.inputs)))
        if set(by_index) != expected:
            raise ValueError("embedding_index_mismatch")
        vectors: list[tuple[float, ...]] = []
        for index in range(len(request.inputs)):
            vector = by_index[index]
            if len(vector) != request.dimensions:
                raise ValueError("embedding_dimension_mismatch")
            vectors.append(vector)
        usage = getattr(response, "usage", None)
        prompt_tokens = 0
        if usage is not None:
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        cost = (
            Decimal(prompt_tokens) * _OPENAI_LARGE_USD_PER_MILLION / Decimal(1_000_000)
        )
        request_id = str(getattr(response, "id", "") or "")
        if not request_id:
            digest = hashlib.sha256(
                "|".join(request.inputs).encode("utf-8")
            ).hexdigest()[:16]
            request_id = f"openai-embed-{digest}"
        return EmbeddingResponse(
            mode="openai",
            vectors=tuple(vectors),
            provider_request_id=request_id,
            fixture_provenance=(
                f"openai://embeddings/{EMBEDDING_MODEL}/{EMBEDDING_DIMENSIONS}"
            ),
            estimated_cost_usd=cost,
        )


class EmbeddingGateway:
    """Shared embedding boundary used by ingestion and Hybrid retrieve."""

    def __init__(self, adapter: EmbeddingAdapter) -> None:
        """Bind one embedding adapter implementation.

        Args:
            adapter: Mock or OpenAI adapter. Callers must not bypass this
                gateway with a second embeddings client.
        """

        self._adapter = adapter

    @model_call_traceable(name="embedding.embed", run_type="embedding")
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Delegate one validated batch to the configured adapter.

        Args:
            request: Bounded embedding batch.

        Returns:
            Provenance-marked vectors plus usage metadata.

        Side Effects:
            Creates a LangSmith span when tracing is enabled. Exported
            fields are hashes and counts, never input text or vectors.
        """

        return await self._adapter.embed(request)


def create_embedding_gateway(settings: SharedSettings) -> EmbeddingGateway:
    """Create the lifecycle-scoped embedding gateway.

    Args:
        settings: Validated deployable settings.

    Returns:
        Mock embedding gateway while ``MOCK_MODEL_MODE`` is true; otherwise
        the pinned OpenAI adapter.

    Raises:
        ModelGatewayUnavailableError: If real-model embeddings are requested
            without ``OPENAI_API_KEY``.
    """

    from smart_rag_core.gateways.model import ModelGatewayUnavailableError

    configure_langsmith(settings)
    if settings.mock_model_mode:
        return EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id=settings.mock_fixture_id)
        )
    secret = settings.openai_api_key
    if secret is None or not secret.get_secret_value().strip():
        raise ModelGatewayUnavailableError(
            "OPENAI_API_KEY is required outside mock mode"
        )
    return EmbeddingGateway(OpenAIEmbeddingAdapter(api_key=secret.get_secret_value()))
