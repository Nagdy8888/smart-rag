"""Request/response contracts and shared model-gateway errors."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.query_answer.versions import (
    ANSWER_MODEL_ID,
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    CONVERSATION_TITLE_MODEL_ID,
    CONVERSATION_TITLE_PROMPT_SHA256,
    CONVERSATION_TITLE_PROMPT_VERSION,
    EVAL_JUDGE_MODEL_ID,
    EVAL_JUDGE_PROMPT_SHA256,
    EVAL_JUDGE_PROMPT_VERSION,
    GENERAL_CHAT_PROMPT_SHA256,
    GENERAL_CHAT_PROMPT_VERSION,
    VERIFIER_MODEL_ID,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)
from smart_rag_core.query_profile.models import ModelInferredProfile
from smart_rag_core.query_profile.versions import (
    PROFILE_MODEL_ID,
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_LLM_TIMEOUT_SECONDS,
    LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
)
from smart_rag_core.retrieval.profiles import RERANK_MODEL_ID
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)

OPENAI_API_HOST = "api.openai.com"


def string_tuple(value: object) -> tuple[str, ...]:
    """Coerce a JSON array field to a string tuple.

    Args:
        value: Mapping value, typically a list of IDs or ranges.

    Returns:
        String tuple. Empty when the value is missing or not a sequence.
    """

    if value is None or isinstance(value, (str, bytes)):
        return ()
    if isinstance(value, (list, tuple)):
        sequence = cast(Sequence[object], value)
        return tuple(str(item) for item in sequence)
    return ()


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
        prompt_text: Prompt body used as Responses instructions.
        model_id: Allow-listed profile model.
        remaining_deadline_seconds: Client timeout bound.
        recent_memory: Delimited untrusted conversation memory.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["query_profile"] = "query_profile"
    query: str = Field(min_length=1, max_length=2000)
    prompt_version: str = PROFILE_PROMPT_VERSION
    prompt_sha256: str = PROFILE_PROMPT_SHA256
    prompt_text: str = Field(default="query_profile", min_length=1, max_length=16_384)
    model_id: str = PROFILE_MODEL_ID
    remaining_deadline_seconds: float = Field(default=25.0, gt=0, le=50)
    recent_memory: str = Field(default="", max_length=16_384)


class QueryProfileModelResponse(BaseModel):
    """Structured profile payload plus usage for one operation.

    Attributes:
        mode: Adapter mode.
        payload: JSON object covering ``PreparationModelPayload`` fields.
        request_id: Provider or fixture id.
        input_tokens: Usage input tokens.
        output_tokens: Usage output tokens.
        model_calls: Always 1 when this response is returned.
        retrieval_performed: Always false.
        inferred: Offline profiler compatibility object.
        fixture_provenance: Mock fixture URI when present.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock", "openai"]
    payload: dict[str, object]
    request_id: str = Field(min_length=1, max_length=128)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    model_calls: Literal[1] = 1
    retrieval_performed: Literal[False] = False
    inferred: ModelInferredProfile = Field(default_factory=ModelInferredProfile)
    fixture_provenance: str = Field(default="", max_length=256)


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


class AnswerModelRequest(BaseModel):
    """Bounded structured answer request. No tools or retrieval.

    Attributes:
        operation: Must be ``answer``.
        query: Original user query.
        prompt_version: Pinned answer prompt version.
        prompt_sha256: Hash of that prompt file.
        prompt_text: Prompt body used as Responses instructions.
        model_id: Allow-listed model.
        source_records: Delimited untrusted canonical records.
        chunk_ids: Canonical IDs the model may cite.
        table_ids: Table IDs the model may cite.
        remaining_deadline_seconds: Client timeout bound.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["answer"] = "answer"
    query: str = Field(min_length=1, max_length=2000)
    prompt_version: str = ANSWER_PROMPT_VERSION
    prompt_sha256: str = ANSWER_PROMPT_SHA256
    prompt_text: str = Field(min_length=1, max_length=16_384)
    model_id: str = ANSWER_MODEL_ID
    source_records: str = Field(max_length=65_536)
    chunk_ids: tuple[str, ...] = ()
    table_ids: tuple[str, ...] = ()
    remaining_deadline_seconds: float = Field(gt=0, le=50)


class AnswerModelResponse(BaseModel):
    """Structured answer payload plus usage for one operation.

    Attributes:
        mode: Adapter mode.
        payload: JSON object awaiting application ID filtering.
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


class GeneralChatModelRequest(BaseModel):
    """Bounded no-source general-chat request. No tools or retrieval.

    Attributes:
        operation: Must be ``general_chat``.
        query: Original user query.
        recent_memory: Delimited untrusted conversation memory.
        knowledge_scope: ``general_knowledge`` or ``user_supplied_text``.
        prompt_version: Pinned general-chat prompt version.
        prompt_sha256: Hash of that prompt file.
        prompt_text: Prompt body used as Responses instructions.
        model_id: Existing allow-listed answer model.
        remaining_deadline_seconds: Client timeout bound.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["general_chat"] = "general_chat"
    query: str = Field(min_length=1, max_length=2000)
    recent_memory: str = Field(default="", max_length=16_384)
    knowledge_scope: KnowledgeScope
    prompt_version: str = GENERAL_CHAT_PROMPT_VERSION
    prompt_sha256: str = GENERAL_CHAT_PROMPT_SHA256
    prompt_text: str = Field(min_length=1, max_length=16_384)
    model_id: str = ANSWER_MODEL_ID
    remaining_deadline_seconds: float = Field(gt=0, le=50)


class GeneralChatModelResponse(BaseModel):
    """Structured general-chat payload plus usage for one operation.

    Attributes:
        mode: Adapter mode.
        payload: JSON object with ``answer_text`` and ``status`` only.
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


class ConversationTitleModelRequest(BaseModel):
    """Bounded session-title request. No tools or retrieval.

    Attributes:
        operation: Must be ``conversation_title``.
        user_excerpt: First user message. Untrusted.
        assistant_excerpt: First assistant message. Untrusted. May be empty.
        prompt_version: Pinned title prompt version.
        prompt_sha256: Hash of that prompt file.
        prompt_text: Prompt body used as Responses instructions.
        model_id: Existing allow-listed answer model.
        remaining_deadline_seconds: Client timeout bound.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["conversation_title"] = "conversation_title"
    user_excerpt: str = Field(min_length=1, max_length=2000)
    assistant_excerpt: str = Field(default="", max_length=2000)
    prompt_version: str = CONVERSATION_TITLE_PROMPT_VERSION
    prompt_sha256: str = CONVERSATION_TITLE_PROMPT_SHA256
    prompt_text: str = Field(min_length=1, max_length=16_384)
    model_id: str = CONVERSATION_TITLE_MODEL_ID
    remaining_deadline_seconds: float = Field(gt=0, le=15)


class ConversationTitleModelResponse(BaseModel):
    """Structured session-title payload plus usage for one operation.

    Attributes:
        mode: Adapter mode.
        payload: JSON object with ``title`` only.
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


class VerifierModelRequest(BaseModel):
    """Bounded structured verifier request. No tools or retrieval.

    Attributes:
        operation: Must be ``verifier``.
        prompt_version: Pinned verifier prompt version.
        prompt_sha256: Hash of that prompt file.
        prompt_text: Prompt body used as Responses instructions.
        model_id: Allow-listed small model.
        source_records: Delimited untrusted canonical records.
        links: At most six atomic-link mappings.
        remaining_deadline_seconds: Client timeout bound.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["verifier"] = "verifier"
    prompt_version: str = VERIFIER_PROMPT_VERSION
    prompt_sha256: str = VERIFIER_PROMPT_SHA256
    prompt_text: str = Field(min_length=1, max_length=16_384)
    model_id: str = VERIFIER_MODEL_ID
    source_records: str = Field(max_length=65_536)
    links: tuple[dict[str, object], ...] = Field(max_length=6)
    remaining_deadline_seconds: float = Field(gt=0, le=50)


class VerifierModelResponse(BaseModel):
    """Structured verifier payload plus usage for one operation.

    Attributes:
        mode: Adapter mode.
        payload: JSON object awaiting application filtering.
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


class EvalJudgeModelRequest(BaseModel):
    """Bounded synthetic-eval judge request. No tools or retrieval.

    Attributes:
        operation: Must be ``eval_judge``.
        prompt_version: Pinned judge prompt version.
        prompt_sha256: Hash of that prompt file.
        prompt_text: Prompt body used as Responses instructions.
        model_id: Allow-listed small model.
        question: Synthetic evaluation question.
        acceptable_answers: Frozen acceptable answers, possibly empty.
        answer_text: Agent answer text.
        answer_status: ``complete``, ``partial``, or ``refused``.
        evidence_ids: Bounded selected synthetic evidence identifiers.
        remaining_deadline_seconds: Client timeout bound.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["eval_judge"] = "eval_judge"
    prompt_version: str = EVAL_JUDGE_PROMPT_VERSION
    prompt_sha256: str = EVAL_JUDGE_PROMPT_SHA256
    prompt_text: str = Field(min_length=1, max_length=16_384)
    model_id: str = EVAL_JUDGE_MODEL_ID
    question: str = Field(min_length=1, max_length=2000)
    acceptable_answers: tuple[str, ...] = ()
    answer_text: str = Field(max_length=16_384)
    answer_status: str = Field(max_length=32)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=24)
    remaining_deadline_seconds: float = Field(gt=0, le=50)


class EvalJudgeModelResponse(BaseModel):
    """Structured eval-judge payload plus usage for one operation.

    Attributes:
        mode: Adapter mode.
        payload: JSON object with unit-interval scores and a short rationale.
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
        timeout_seconds: Provider client timeout in seconds. Must stay below
            the vendor LightRAG ``wait_for`` bound.
    """

    model_config = ConfigDict(frozen=True)

    operation: Literal["lightrag_llm"] = "lightrag_llm"
    role: Literal["extract", "keyword", "query", "vlm", "other"]
    prompt: str = Field(default="", max_length=65_536)
    system_prompt: str = Field(default="", max_length=65_536)
    timeout_seconds: float = Field(
        default=LIGHTRAG_LLM_TIMEOUT_SECONDS,
        gt=0,
        le=LIGHTRAG_LLM_VENDOR_TIMEOUT_SECONDS,
    )


class LightRagLlmResponse(BaseModel):
    """LightRAG callback payload. Never a company-knowledge answer.

    Attributes:
        mode: Adapter mode. ``mock`` for fixtures, ``local`` for a deliberately
            provider-free callback, and ``openai`` for live extract.
        content: Bounded callback text. Extract uses vendor tuple format.
        fixture_provenance: Fixture URI. Empty for live OpenAI extract.
        provider_request_id: Provider response id. Empty without a live call.
        model_id: Provider model id. Empty without a live call.
        input_tokens: Provider-reported total input tokens.
        cached_input_tokens: Provider-reported cached subset of input tokens.
        output_tokens: Provider-reported output tokens.
        total_tokens: Input plus output tokens.
        model_calls: One for live extract, otherwise zero.
        estimated_cost_usd: Standard API list-price estimate. The provider
            invoice remains canonical.
        pricing_version: Published price source/version used by the estimate.
        retrieval_performed: Always false.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["mock", "local", "openai"]
    content: str = Field(max_length=32_768)
    fixture_provenance: str = Field(default="", max_length=256)
    provider_request_id: str = Field(default="", max_length=128)
    model_id: str = Field(default="", max_length=128)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0, le=1)
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)
    pricing_version: str = Field(default="", max_length=128)
    retrieval_performed: Literal[False] = False


def mock_lightrag_llm_content(role: str) -> str:
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
