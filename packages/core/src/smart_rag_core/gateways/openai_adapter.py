"""Live OpenAI adapter for counted profile, answer, and retrieval calls."""

from __future__ import annotations

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
    ModelGatewayUnavailableError,
    ModelRequest,
    ModelResponse,
    QueryProfileModelRequest,
    QueryProfileModelResponse,
    RerankModelRequest,
    RerankModelResponse,
    VerifierModelRequest,
    VerifierModelResponse,
    mock_lightrag_llm_content,
)
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
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_LLM_MAX_INPUT_CHARS,
    LIGHTRAG_LLM_MODEL_ID,
    LIGHTRAG_LLM_PRICING_VERSION,
)
from smart_rag_core.retrieval.rerank import rerank_input_hash


class OpenAIRerankAdapter:
    """Live OpenAI adapter for counted profile, answer, and retrieval calls."""

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
        """Execute one Responses query-profile operation.

        Args:
            request: Bounded profile request.

        Returns:
            Provider JSON payload plus usage.

        Raises:
            OpenAIProfileError: Typed provider failure.
            ValueError: Input bound errors.

        Side Effects:
            One HTTPS call with ``max_retries=0`` and ``store=False``.
        """

        joined = request.query + request.recent_memory
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        payload, request_id, input_tokens, output_tokens = execute_openai_query_profile(
            api_key=self._api_key,
            prompt_text=request.prompt_text,
            prompt_sha256=request.prompt_sha256,
            prompt_version=request.prompt_version,
            model_id=request.model_id,
            user_query=request.query,
            recent_memory=request.recent_memory,
            timeout_seconds=request.remaining_deadline_seconds,
        )
        return QueryProfileModelResponse(
            mode="openai",
            payload=payload,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

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

    async def generate_answer(self, request: AnswerModelRequest) -> AnswerModelResponse:
        """Execute one Responses answer operation.

        Args:
            request: Bounded answer request.

        Returns:
            Provider JSON payload plus usage.

        Raises:
            OpenAIAnswerError: Typed provider failure.
            ValueError: Input bound errors.

        Side Effects:
            One HTTPS call with ``max_retries=0``.
        """

        joined = request.query + request.source_records
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        payload, request_id, input_tokens, output_tokens = execute_openai_answer(
            api_key=self._api_key,
            prompt_text=request.prompt_text,
            prompt_sha256=request.prompt_sha256,
            prompt_version=request.prompt_version,
            model_id=request.model_id,
            user_query=request.query,
            source_records=request.source_records,
            timeout_seconds=request.remaining_deadline_seconds,
        )
        return AnswerModelResponse(
            mode="openai",
            payload=payload,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_general_chat(
        self, request: GeneralChatModelRequest
    ) -> GeneralChatModelResponse:
        """Execute one Responses general-chat operation.

        Args:
            request: Bounded general-chat request.

        Returns:
            Provider JSON payload plus usage.

        Raises:
            OpenAIAnswerError: Typed provider failure.
            ValueError: Input bound errors.

        Side Effects:
            One HTTPS call with ``max_retries=0`` and ``store=False``.
        """

        joined = request.query + request.recent_memory
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        payload, request_id, input_tokens, output_tokens = execute_openai_general_chat(
            api_key=self._api_key,
            prompt_text=request.prompt_text,
            prompt_sha256=request.prompt_sha256,
            prompt_version=request.prompt_version,
            model_id=request.model_id,
            user_query=request.query,
            recent_memory=request.recent_memory,
            knowledge_scope=request.knowledge_scope,
            timeout_seconds=request.remaining_deadline_seconds,
        )
        return GeneralChatModelResponse(
            mode="openai",
            payload=payload,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_conversation_title(
        self, request: ConversationTitleModelRequest
    ) -> ConversationTitleModelResponse:
        """Execute one Responses session-title operation.

        Args:
            request: Bounded title request.

        Returns:
            Provider JSON payload plus usage.

        Raises:
            OpenAIAnswerError: Typed provider failure.
            ValueError: Input bound errors.

        Side Effects:
            One HTTPS call with ``max_retries=0`` and ``store=False``.
        """

        joined = request.user_excerpt + request.assistant_excerpt
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        payload, request_id, input_tokens, output_tokens = (
            execute_openai_conversation_title(
                api_key=self._api_key,
                prompt_text=request.prompt_text,
                prompt_sha256=request.prompt_sha256,
                prompt_version=request.prompt_version,
                model_id=request.model_id,
                user_excerpt=request.user_excerpt,
                assistant_excerpt=request.assistant_excerpt,
                timeout_seconds=request.remaining_deadline_seconds,
            )
        )
        return ConversationTitleModelResponse(
            mode="openai",
            payload=payload,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_verifier(
        self, request: VerifierModelRequest
    ) -> VerifierModelResponse:
        """Execute one Responses verifier operation.

        Args:
            request: Bounded verifier request.

        Returns:
            Provider JSON payload plus usage.

        Raises:
            OpenAIAnswerError: Typed provider failure.
            ValueError: Batch cap or input bound errors.

        Side Effects:
            One HTTPS call with ``max_retries=0``.
        """

        if len(request.links) > 6:
            raise ValueError("verifier_batch_cap")
        if len(request.source_records) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        link_ids = tuple(str(item.get("link_id") or "") for item in request.links)
        payload, request_id, input_tokens, output_tokens = execute_openai_verifier(
            api_key=self._api_key,
            prompt_text=request.prompt_text,
            prompt_sha256=request.prompt_sha256,
            prompt_version=request.prompt_version,
            model_id=request.model_id,
            source_records=request.source_records,
            link_payload=list(request.links),
            link_ids=link_ids,
            timeout_seconds=request.remaining_deadline_seconds,
        )
        return VerifierModelResponse(
            mode="openai",
            payload=payload,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_eval_judge(
        self, request: EvalJudgeModelRequest
    ) -> EvalJudgeModelResponse:
        """Execute one Responses synthetic-eval judge operation.

        Args:
            request: Bounded judge request.

        Returns:
            Provider JSON payload plus usage.

        Raises:
            OpenAIAnswerError: Typed provider failure.
            ValueError: Input bound errors.

        Side Effects:
            One HTTPS call with ``max_retries=0``.
        """

        joined = (
            request.question + request.answer_text + "".join(request.acceptable_answers)
        )
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        user_payload: dict[str, object] = {
            "question": request.question,
            "acceptable_answers": list(request.acceptable_answers),
            "answer_text": request.answer_text,
            "answer_status": request.answer_status,
            "evidence_ids": list(request.evidence_ids),
        }
        payload, request_id, input_tokens, output_tokens = execute_openai_eval_judge(
            api_key=self._api_key,
            prompt_text=request.prompt_text,
            prompt_sha256=request.prompt_sha256,
            prompt_version=request.prompt_version,
            model_id=request.model_id,
            user_payload=user_payload,
            timeout_seconds=request.remaining_deadline_seconds,
        )
        return EvalJudgeModelResponse(
            mode="openai",
            payload=payload,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def generate_lightrag_llm(
        self, request: LightRagLlmRequest
    ) -> LightRagLlmResponse:
        """Run one LightRAG extract call, or return local fixtures.

        Args:
            request: LightRAG callback request.

        Returns:
            Provider extract text for ``extract``. Keyword and query roles
            return bounded local fixtures without a provider call so ingest
            cannot silently generate LightRAG answers.

        Raises:
            ModelGatewayUnavailableError: For ``vlm`` and ``other`` roles.
            OpenAILightragError: Provider timeout, auth, HTTP, or empty output.
            ValueError: Combined extract input exceeds the bound.

        Side Effects:
            One HTTPS Responses call for ``extract`` with ``max_retries=0``.
            Keyword and query roles do not call OpenAI.
        """

        if request.role == "keyword":
            return LightRagLlmResponse(
                mode="local",
                content=mock_lightrag_llm_content("keyword"),
                fixture_provenance="",
                retrieval_performed=False,
            )
        if request.role == "query":
            return LightRagLlmResponse(
                mode="local",
                content=mock_lightrag_llm_content("query"),
                fixture_provenance="",
                retrieval_performed=False,
            )
        if request.role != "extract":
            raise ModelGatewayUnavailableError("lightrag_llm_role_not_configured")
        combined = request.system_prompt + request.prompt
        input_bound = min(self._max_input_chars, LIGHTRAG_LLM_MAX_INPUT_CHARS)
        if len(combined) > input_bound:
            raise ValueError(
                f"Model input exceeds configured {input_bound}-character bound"
            )
        (
            content,
            request_id,
            input_tokens,
            cached_input_tokens,
            output_tokens,
            estimated_cost_usd,
        ) = execute_openai_lightrag_llm(
            api_key=self._api_key,
            model_id=LIGHTRAG_LLM_MODEL_ID,
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            timeout_seconds=request.timeout_seconds,
        )
        return LightRagLlmResponse(
            mode="openai",
            content=content,
            fixture_provenance="",
            provider_request_id=request_id,
            model_id=LIGHTRAG_LLM_MODEL_ID,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model_calls=1,
            estimated_cost_usd=estimated_cost_usd,
            pricing_version=LIGHTRAG_LLM_PRICING_VERSION,
            retrieval_performed=False,
        )
