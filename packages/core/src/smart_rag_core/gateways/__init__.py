"""External integration boundaries owned by the Smart RAG core package."""

from smart_rag_core.gateways.embedding import (
    EmbeddingGateway,
    EmbeddingRequest,
    EmbeddingResponse,
    create_embedding_gateway,
)
from smart_rag_core.gateways.model import (
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
    block_openai_network,
    create_model_gateway,
)

__all__ = [
    "EmbeddingGateway",
    "EmbeddingRequest",
    "EmbeddingResponse",
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
    "block_openai_network",
    "create_embedding_gateway",
    "create_model_gateway",
]
