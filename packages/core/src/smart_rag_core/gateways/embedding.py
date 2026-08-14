"""Embedding gateway types and mock adapter for governed ingestion proofs."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.ingestion.embeddings.mock_vectors import mock_embedding_vector
from smart_rag_core.observability.langsmith_tracing import (
    configure_langsmith,
    model_call_traceable,
)
from smart_rag_core.settings import SharedSettings


class EmbeddingRequest(BaseModel):
    """Bounded embedding batch accepted by the shared gateway."""

    model_config = ConfigDict(frozen=True)

    operation_key: str = Field(min_length=1, max_length=256)
    inputs: tuple[str, ...] = Field(min_length=1)
    model: str = Field(min_length=1, max_length=128)
    dimensions: int = Field(ge=1, le=3072)


class EmbeddingResponse(BaseModel):
    """Provenance-marked embedding batch response."""

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock"]
    vectors: tuple[tuple[float, ...], ...]
    provider_request_id: str
    fixture_provenance: str
    estimated_cost_usd: Decimal = Decimal("0")


class EmbeddingAdapter(Protocol):
    """Protocol implemented by embedding provider adapters."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed one bounded batch."""

        ...


class MockEmbeddingAdapter:
    """Deterministic embedding adapter with no provider network access."""

    def __init__(self, *, fixture_id: str) -> None:
        """Initialize deterministic fixture metadata."""

        self._fixture_id = fixture_id

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return deterministic unit vectors keyed by contextual input text."""

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


class EmbeddingGateway:
    """Shared embedding boundary used by ingestion services."""

    def __init__(self, adapter: EmbeddingAdapter) -> None:
        """Bind one embedding adapter implementation."""

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
        Mock embedding gateway while ``MOCK_MODEL_MODE`` is true.

    Raises:
        ModelGatewayUnavailableError: If real-model embeddings are requested
            before the verified OpenAI adapter exists.
    """

    configure_langsmith(settings)
    if not settings.mock_model_mode:
        from smart_rag_core.gateways.model import ModelGatewayUnavailableError

        raise ModelGatewayUnavailableError(
            "Real OpenAI embedding adapter requires verified provider settings"
        )
    return EmbeddingGateway(MockEmbeddingAdapter(fixture_id=settings.mock_fixture_id))
