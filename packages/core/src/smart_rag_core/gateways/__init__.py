"""External integration boundaries owned by the Smart RAG core package."""

from smart_rag_core.gateways.model import (
    MockModelAdapter,
    MockModelNetworkDeniedError,
    ModelGateway,
    ModelGatewayUnavailableError,
    ModelRequest,
    ModelResponse,
    block_openai_network,
    create_model_gateway,
)

__all__ = [
    "MockModelAdapter",
    "MockModelNetworkDeniedError",
    "ModelGateway",
    "ModelGatewayUnavailableError",
    "ModelRequest",
    "ModelResponse",
    "block_openai_network",
    "create_model_gateway",
]
