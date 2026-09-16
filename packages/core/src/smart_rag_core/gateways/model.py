"""Compatibility facade for the model gateway public surface."""

from smart_rag_core.gateways.mock_model import MockModelAdapter
from smart_rag_core.gateways.model_gateway import (
    ModelGateway,
    block_openai_network,
    create_model_gateway,
)
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
    ModelInputBoundError,
    ModelRequest,
    ModelResponse,
    QueryProfileModelRequest,
    QueryProfileModelResponse,
    RerankModelRequest,
    RerankModelResponse,
    VerifierModelRequest,
    VerifierModelResponse,
)
from smart_rag_core.gateways.openai_adapter import OpenAIRerankAdapter
from smart_rag_core.gateways.openai_answer import (
    execute_openai_answer,
    execute_openai_eval_judge,
    execute_openai_verifier,
)
from smart_rag_core.gateways.openai_conversation_title import (
    execute_openai_conversation_title,
)
from smart_rag_core.gateways.openai_general_chat import execute_openai_general_chat
from smart_rag_core.gateways.openai_lightrag import execute_openai_lightrag_llm
from smart_rag_core.gateways.openai_profile import execute_openai_query_profile
from smart_rag_core.gateways.openai_rerank import execute_openai_rerank

__all__ = [
    "OPENAI_API_HOST",
    "AnswerModelRequest",
    "AnswerModelResponse",
    "ConversationTitleModelRequest",
    "ConversationTitleModelResponse",
    "EvalJudgeModelRequest",
    "EvalJudgeModelResponse",
    "GeneralChatModelRequest",
    "GeneralChatModelResponse",
    "LightRagLlmRequest",
    "LightRagLlmResponse",
    "MockModelAdapter",
    "MockModelNetworkDeniedError",
    "ModelAdapter",
    "ModelGateway",
    "ModelGatewayUnavailableError",
    "ModelInputBoundError",
    "ModelRequest",
    "ModelResponse",
    "OpenAIRerankAdapter",
    "QueryProfileModelRequest",
    "QueryProfileModelResponse",
    "RerankModelRequest",
    "RerankModelResponse",
    "VerifierModelRequest",
    "VerifierModelResponse",
    "block_openai_network",
    "create_model_gateway",
    "execute_openai_answer",
    "execute_openai_conversation_title",
    "execute_openai_eval_judge",
    "execute_openai_general_chat",
    "execute_openai_lightrag_llm",
    "execute_openai_query_profile",
    "execute_openai_rerank",
    "execute_openai_verifier",
]
