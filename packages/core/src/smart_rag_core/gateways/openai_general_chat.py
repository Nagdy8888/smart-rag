"""OpenAI Responses adapter for one no-source general-chat call."""

from __future__ import annotations

import json
from typing import cast

from openai import APIStatusError, APITimeoutError, AuthenticationError

from smart_rag_core.gateways.openai_answer import OpenAIAnswerError
from smart_rag_core.observability.langsmith_tracing import (
    general_chat_responses_traceable,
    traced_openai_client,
)
from smart_rag_core.query_answer.schemas import general_chat_json_schema
from smart_rag_core.query_answer.versions import (
    ALLOWED_ANSWER_MODEL_IDS,
    ANSWER_MAX_OUTPUT_TOKENS,
    GENERAL_CHAT_PROMPT_SHA256,
    GENERAL_CHAT_PROMPT_VERSION,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope


@general_chat_responses_traceable
def execute_openai_general_chat(
    *,
    api_key: str,
    prompt_text: str,
    prompt_sha256: str,
    prompt_version: str,
    model_id: str,
    user_query: str,
    recent_memory: str,
    knowledge_scope: KnowledgeScope,
    timeout_seconds: float,
) -> tuple[dict[str, object], str, int, int]:
    """Make exactly one structured general-chat Responses call.

    Args:
        api_key: Provider credential. Never logged.
        prompt_text: Pinned general-chat prompt body.
        prompt_sha256: Expected prompt digest.
        prompt_version: Expected prompt version.
        model_id: Allow-listed answer model. No new model name.
        user_query: Original user text.
        recent_memory: Delimited untrusted conversation memory.
        knowledge_scope: ``general_knowledge`` or ``user_supplied_text``.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Parsed JSON payload, provider request id, input tokens, output tokens.

    Raises:
        OpenAIAnswerError: Timeout, auth, HTTP, version, or parse failures.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. ``store=False``.
        No tools or retrieval. When LangSmith tracing is enabled, a redacted
        ``openai.responses.general_chat`` span is exported.
    """

    if (
        prompt_version != GENERAL_CHAT_PROMPT_VERSION
        or prompt_sha256 != GENERAL_CHAT_PROMPT_SHA256
    ):
        raise OpenAIAnswerError("general_chat_version_mismatch")
    if model_id not in ALLOWED_ANSWER_MODEL_IDS:
        raise OpenAIAnswerError("general_chat_version_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIAnswerError("answer_budget_denied")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    user_payload = {
        "query": user_query,
        "memory": recent_memory,
        "knowledge_scope": knowledge_scope.value,
    }
    try:
        response = client.responses.create(
            model=model_id,
            instructions=prompt_text,
            input=json.dumps(user_payload, separators=(",", ":")),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "general_chat_answer",
                    "strict": True,
                    "schema": general_chat_json_schema(),
                }
            },
            max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS,
            store=False,
        )
    except APITimeoutError as error:
        raise OpenAIAnswerError("answer_timeout") from error
    except AuthenticationError as error:
        raise OpenAIAnswerError("answer_provider_error") from error
    except APIStatusError as error:
        if error.status_code == 429:
            raise OpenAIAnswerError("answer_budget_denied") from error
        raise OpenAIAnswerError("answer_provider_error") from error
    return _parse_general_chat_response(response)


def _parse_general_chat_response(
    response: object,
) -> tuple[dict[str, object], str, int, int]:
    """Parse one Responses object into JSON plus usage.

    Args:
        response: Provider response.

    Returns:
        Payload, request id, input tokens, output tokens.

    Raises:
        OpenAIAnswerError: Incomplete or invalid JSON.
    """

    request_id = str(getattr(response, "id", "") or "unknown")
    status = getattr(response, "status", None)
    if status not in {None, "completed"}:
        raise OpenAIAnswerError("general_chat_incomplete")
    usage = getattr(response, "usage", None)
    if usage is None:
        raise OpenAIAnswerError("general_chat_unknown_usage")
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    text = getattr(response, "output_text", "") or ""
    if not str(text).strip():
        raise OpenAIAnswerError("general_chat_incomplete")
    try:
        loaded: object = json.loads(str(text))
    except json.JSONDecodeError as error:
        raise OpenAIAnswerError("general_chat_schema_invalid") from error
    if not isinstance(loaded, dict):
        raise OpenAIAnswerError("general_chat_schema_invalid")
    return cast(dict[str, object], loaded), request_id, input_tokens, output_tokens
