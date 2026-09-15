"""External integration boundaries owned by the Smart RAG core package.

Model adapters are imported lazily. Eagerly importing ``gateways.model``
pulls answer/verifier schemas, fusion, and routing, which circularly
imports ``query_admission.ceilings`` while that module is still loading
(storage → gateways → model → query_answer → fusion → routing → ceilings).
"""

from typing import TYPE_CHECKING, Any

from smart_rag_core.gateways.embedding import (
    EmbeddingGateway,
    EmbeddingRequest,
    EmbeddingResponse,
    create_embedding_gateway,
)

if TYPE_CHECKING:
    from smart_rag_core.gateways.exa_search import (
        ExaContentItem,
        ExaContentsResponse,
        ExaProviderMetadata,
        ExaSearchCandidate,
        ExaSearchError,
        ExaSearchGateway,
        ExaSearchResponse,
        create_exa_search_gateway,
    )
    from smart_rag_core.gateways.model import (
        AnswerModelRequest,
        AnswerModelResponse,
        LightRagLlmRequest,
        LightRagLlmResponse,
        MockModelAdapter,
        MockModelNetworkDeniedError,
        ModelGateway,
        ModelGatewayUnavailableError,
        ModelRequest,
        ModelResponse,
        QueryProfileModelRequest,
        QueryProfileModelResponse,
        RerankModelRequest,
        RerankModelResponse,
        VerifierModelRequest,
        VerifierModelResponse,
        block_openai_network,
        create_model_gateway,
    )

_EXA_EXPORTS = frozenset(
    {
        "ExaContentItem",
        "ExaContentsResponse",
        "ExaProviderMetadata",
        "ExaSearchCandidate",
        "ExaSearchError",
        "ExaSearchGateway",
        "ExaSearchResponse",
        "create_exa_search_gateway",
    }
)

_MODEL_EXPORTS = frozenset(
    {
        "AnswerModelRequest",
        "AnswerModelResponse",
        "LightRagLlmRequest",
        "LightRagLlmResponse",
        "MockModelAdapter",
        "MockModelNetworkDeniedError",
        "ModelGateway",
        "ModelGatewayUnavailableError",
        "ModelRequest",
        "ModelResponse",
        "QueryProfileModelRequest",
        "QueryProfileModelResponse",
        "RerankModelRequest",
        "RerankModelResponse",
        "VerifierModelRequest",
        "VerifierModelResponse",
        "block_openai_network",
        "create_model_gateway",
    }
)

__all__ = [
    "AnswerModelRequest",
    "AnswerModelResponse",
    "EmbeddingGateway",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "ExaContentItem",
    "ExaContentsResponse",
    "ExaProviderMetadata",
    "ExaSearchCandidate",
    "ExaSearchError",
    "ExaSearchGateway",
    "ExaSearchResponse",
    "LightRagLlmRequest",
    "LightRagLlmResponse",
    "MockModelAdapter",
    "MockModelNetworkDeniedError",
    "ModelGateway",
    "ModelGatewayUnavailableError",
    "ModelRequest",
    "ModelResponse",
    "QueryProfileModelRequest",
    "QueryProfileModelResponse",
    "RerankModelRequest",
    "RerankModelResponse",
    "VerifierModelRequest",
    "VerifierModelResponse",
    "block_openai_network",
    "create_embedding_gateway",
    "create_exa_search_gateway",
    "create_model_gateway",
]


def __getattr__(name: str) -> Any:
    """Load model and Exa gateway exports on first attribute access.

    Args:
        name: Requested public attribute.

    Returns:
        The lazy module attribute.

    Raises:
        AttributeError: When ``name`` is not a published export.
    """

    if name in _EXA_EXPORTS:
        from smart_rag_core.gateways import exa_search as exa_module

        return getattr(exa_module, name)
    if name not in _MODEL_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from smart_rag_core.gateways import model as model_module

    return getattr(model_module, name)


def __dir__() -> list[str]:
    """List lazy Exa and model exports alongside eager embedding symbols.

    Returns:
        Sorted public names for tab completion and ``dir()``.
    """

    return sorted({*globals().keys(), *_MODEL_EXPORTS, *_EXA_EXPORTS})
