"""Counted Hybrid query-embedding send used by ``HybridRetriever``."""

from __future__ import annotations

from typing import cast

from smart_rag_core.gateways.embedding import (
    EmbeddingGateway,
    EmbeddingRequest,
    EmbeddingResponse,
)
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.retrieve_budget import QueryRetrieveBudget
from smart_rag_core.retrieval.hybrid_run.budget import counted_retrieve_send
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.runtime.async_bridge import run_coro_blocking


def embed_query_texts(
    gateway: EmbeddingGateway,
    texts: tuple[str, ...],
    budget: QueryRetrieveBudget | None = None,
) -> tuple[EmbeddingResponse | None, RetrievalFallbackReason | None]:
    """Issue one batched gateway embedding call.

    Args:
        gateway: Shared embedding boundary. No bypass client.
        texts: Unique original plus variants, already bounded.
        budget: Optional retrieve ledger. When set, the batch consumes
            the run-local reservation before the provider call.

    Returns:
        Response and optional fallback when the gateway fails or
        remaining cannot cover the embedding kind cap.
    """

    request = EmbeddingRequest(
        operation_key="hybrid.query_embed",
        inputs=texts,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSIONS,
    )

    def _send() -> EmbeddingResponse:
        """Await the embedding gateway from this sync retrieve.

        Returns:
            Embedding response.

        Raises:
            Exception: Provider or loop failures. Mapped to dense
                unavailable by the caller.
        """

        result = run_coro_blocking(gateway.embed(request))
        return cast(EmbeddingResponse, result)

    try:
        response = cast(
            EmbeddingResponse,
            counted_retrieve_send(
                budget,
                usage_kind="embedding",
                model_id=EMBEDDING_MODEL,
                send=_send,
            ),
        )
    except (QueryBudgetError, QueryCeilingError):
        return None, RetrievalFallbackReason.DENSE_UNAVAILABLE
    except Exception:
        return None, RetrievalFallbackReason.DENSE_UNAVAILABLE
    if len(response.vectors) != len(texts):
        return None, RetrievalFallbackReason.DENSE_UNAVAILABLE
    return response, None
