"""Adapter protocol for one counted model operation."""

from __future__ import annotations

from typing import Protocol

from smart_rag_core.gateways.model_types import (
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
from smart_rag_core.gateways.summary_model import (
    SummaryModelRequest,
    SummaryModelResponse,
)


class ModelAdapter(Protocol):
    """Protocol implemented by model provider adapters."""

    async def generate_summary(
        self, request: SummaryModelRequest
    ) -> SummaryModelResponse:
        """Produce one bounded conversation summary."""
        ...

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

    async def generate_answer(self, request: AnswerModelRequest) -> AnswerModelResponse:
        """Generate at most one structured answer payload.

        Args:
            request: Validated answer request.

        Returns:
            Structured answer response.
        """

        ...

    async def generate_general_chat(
        self, request: GeneralChatModelRequest
    ) -> GeneralChatModelResponse:
        """Generate at most one no-source general-chat payload.

        Args:
            request: Validated general-chat request.

        Returns:
            Structured general-chat response.
        """

        ...

    async def generate_web_answer(
        self, request: WebAnswerModelRequest
    ) -> WebAnswerModelResponse:
        """Generate at most one Web-research synthesis payload.

        Args:
            request: Validated Web-answer request.

        Returns:
            Structured Web-answer response.
        """

        ...

    async def generate_conversation_title(
        self, request: ConversationTitleModelRequest
    ) -> ConversationTitleModelResponse:
        """Generate at most one session-title payload.

        Args:
            request: Validated title request.

        Returns:
            Structured title response.
        """

        ...

    async def generate_verifier(
        self, request: VerifierModelRequest
    ) -> VerifierModelResponse:
        """Generate at most one structured verifier payload.

        Args:
            request: Validated verifier request.

        Returns:
            Structured verifier response.
        """

        ...

    async def generate_eval_judge(
        self, request: EvalJudgeModelRequest
    ) -> EvalJudgeModelResponse:
        """Generate at most one structured synthetic-eval judge payload.

        Args:
            request: Validated judge request.

        Returns:
            Structured judge response.
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
