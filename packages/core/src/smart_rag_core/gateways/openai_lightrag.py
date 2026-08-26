"""OpenAI Responses adapter for one LightRAG extract callback.

Vendor extract prompts are not application-owned, so this call does not pin a
prompt SHA. It still pins the model id, disables SDK retries and tools, and
refuses to store provider-side conversation state.
"""

from __future__ import annotations

from decimal import Decimal

from openai import APIStatusError, APITimeoutError, AuthenticationError

from smart_rag_core.observability.langsmith_tracing import (
    lightrag_llm_responses_traceable,
    traced_openai_client,
)
from smart_rag_core.retrieval.graph import (
    ALLOWED_LIGHTRAG_LLM_MODEL_IDS,
    LIGHTRAG_LLM_CACHED_INPUT_USD_PER_MILLION,
    LIGHTRAG_LLM_INPUT_USD_PER_MILLION,
    LIGHTRAG_LLM_MAX_OUTPUT_CHARS,
    LIGHTRAG_LLM_MAX_OUTPUT_TOKENS,
    LIGHTRAG_LLM_MODEL_ID,
    LIGHTRAG_LLM_OUTPUT_USD_PER_MILLION,
)


class OpenAILightragError(RuntimeError):
    """Typed provider failure for one LightRAG extract Responses call."""

    def __init__(self, reason: str) -> None:
        """Store a machine-readable fallback reason.

        Args:
            reason: Short reason code such as ``lightrag_llm_timeout``.
        """

        super().__init__(reason)
        self.reason = reason


@lightrag_llm_responses_traceable
def execute_openai_lightrag_llm(
    *,
    api_key: str,
    model_id: str,
    prompt: str,
    system_prompt: str,
    timeout_seconds: float,
) -> tuple[str, str, int, int, int, Decimal]:
    """Make exactly one free-text Responses call for LightRAG extract.

    Args:
        api_key: Provider credential. Never logged.
        model_id: Allow-listed chat model. Must be ``gpt-4o-mini``.
        prompt: Vendor user/task prompt. Hashed in LangSmith, never copied.
        system_prompt: Vendor system prompt. Empty string omits instructions.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Extract text, provider request id, input tokens, cached input tokens,
        output tokens, and estimated standard-API USD.

    Raises:
        OpenAILightragError: Timeout, auth, HTTP, empty, oversized, or
            incomplete provider output.
        ValueError: If the model id is not allow-listed or the prompt is empty.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. No tools. ``store`` is
        false. When LangSmith tracing is enabled, a redacted
        ``openai.responses.lightrag_llm`` span is exported.
    """

    if model_id not in ALLOWED_LIGHTRAG_LLM_MODEL_IDS:
        raise OpenAILightragError("lightrag_llm_model_mismatch")
    if timeout_seconds <= 0:
        raise OpenAILightragError("lightrag_llm_budget_denied")
    if not prompt.strip():
        raise ValueError("lightrag_llm_empty_prompt")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    try:
        if system_prompt.strip():
            response = client.responses.create(
                model=model_id,
                instructions=system_prompt,
                input=prompt,
                max_output_tokens=LIGHTRAG_LLM_MAX_OUTPUT_TOKENS,
                store=False,
            )
        else:
            response = client.responses.create(
                model=model_id,
                input=prompt,
                max_output_tokens=LIGHTRAG_LLM_MAX_OUTPUT_TOKENS,
                store=False,
            )
    except APITimeoutError as error:
        raise OpenAILightragError("lightrag_llm_timeout") from error
    except AuthenticationError as error:
        raise OpenAILightragError("lightrag_llm_provider_error") from error
    except APIStatusError as error:
        if error.status_code == 429:
            raise OpenAILightragError("lightrag_llm_budget_denied") from error
        raise OpenAILightragError("lightrag_llm_provider_error") from error
    request_id = str(getattr(response, "id", "") or "unknown")
    status = getattr(response, "status", None)
    if status not in {None, "completed"}:
        raise OpenAILightragError("lightrag_llm_incomplete")
    usage = getattr(response, "usage", None)
    if usage is None:
        raise OpenAILightragError("lightrag_llm_unknown_usage")
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    input_details = getattr(usage, "input_tokens_details", None)
    cached_input_tokens = 0
    if input_details is not None:
        cached_input_tokens = int(getattr(input_details, "cached_tokens", 0) or 0)
    cached_input_tokens = min(max(cached_input_tokens, 0), input_tokens)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    text = getattr(response, "output_text", "") or ""
    if not text.strip():
        raise OpenAILightragError("lightrag_llm_incomplete")
    if len(text) > LIGHTRAG_LLM_MAX_OUTPUT_CHARS:
        raise OpenAILightragError("lightrag_llm_incomplete")
    estimated_cost_usd = estimate_lightrag_llm_cost(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )
    return (
        text,
        request_id,
        input_tokens,
        cached_input_tokens,
        output_tokens,
        estimated_cost_usd,
    )


def estimate_lightrag_llm_cost(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> Decimal:
    """Estimate standard-API USD from provider-reported token usage.

    Args:
        input_tokens: Total input tokens, including cached tokens.
        cached_input_tokens: Input tokens billed at the cached-input rate.
        output_tokens: Generated output tokens.

    Returns:
        USD estimate using the pinned published prices. The provider invoice
        remains canonical.

    Raises:
        ValueError: If counts are negative or cached input exceeds total input.
    """

    if min(input_tokens, cached_input_tokens, output_tokens) < 0:
        raise ValueError("lightrag_llm_negative_usage")
    if cached_input_tokens > input_tokens:
        raise ValueError("lightrag_llm_cached_usage_exceeds_input")
    uncached_input_tokens = input_tokens - cached_input_tokens
    one_million = Decimal(1_000_000)
    return (
        Decimal(uncached_input_tokens) * Decimal(LIGHTRAG_LLM_INPUT_USD_PER_MILLION)
        + Decimal(cached_input_tokens)
        * Decimal(LIGHTRAG_LLM_CACHED_INPUT_USD_PER_MILLION)
        + Decimal(output_tokens) * Decimal(LIGHTRAG_LLM_OUTPUT_USD_PER_MILLION)
    ) / one_million


def default_lightrag_llm_model() -> str:
    """Return the allow-listed LightRAG extract model id.

    Returns:
        ``gpt-4o-mini``.
    """

    return LIGHTRAG_LLM_MODEL_ID
