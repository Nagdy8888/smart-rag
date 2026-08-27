"""OpenAI Responses adapter for one session-title call."""

from __future__ import annotations

import json
from typing import cast

from openai import APIStatusError, APITimeoutError, AuthenticationError

from smart_rag_core.conversations.title import conversation_title_json_schema
from smart_rag_core.gateways.openai_answer import OpenAIAnswerError
from smart_rag_core.observability.langsmith_tracing import (
    conversation_title_responses_traceable,
    traced_openai_client,
)
from smart_rag_core.query_answer.versions import (
    ALLOWED_CONVERSATION_TITLE_MODEL_IDS,
    CONVERSATION_TITLE_MAX_OUTPUT_TOKENS,
    CONVERSATION_TITLE_PROMPT_SHA256,
    CONVERSATION_TITLE_PROMPT_VERSION,
)


@conversation_title_responses_traceable
def execute_openai_conversation_title(
    *,
    api_key: str,
    prompt_text: str,
    prompt_sha256: str,
    prompt_version: str,
    model_id: str,
    user_excerpt: str,
    assistant_excerpt: str,
    timeout_seconds: float,
) -> tuple[dict[str, object], str, int, int]:
    """Make exactly one structured session-title Responses call.

    Args:
        api_key: Provider credential. Never logged.
        prompt_text: Pinned title prompt body.
        prompt_sha256: Expected prompt digest.
        prompt_version: Expected prompt version.
        model_id: Allow-listed title model. No new model name.
        user_excerpt: First user message. Untrusted.
        assistant_excerpt: First assistant message. Untrusted. May be empty.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Parsed JSON payload, provider request id, input tokens, output tokens.

    Raises:
        OpenAIAnswerError: Timeout, auth, HTTP, version, or parse failures.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. ``store=False``.
        No tools or retrieval. When LangSmith tracing is enabled, a redacted
        ``openai.responses.conversation_title`` span is exported.
    """

    if (
        prompt_version != CONVERSATION_TITLE_PROMPT_VERSION
        or prompt_sha256 != CONVERSATION_TITLE_PROMPT_SHA256
    ):
        raise OpenAIAnswerError("conversation_title_version_mismatch")
    if model_id not in ALLOWED_CONVERSATION_TITLE_MODEL_IDS:
        raise OpenAIAnswerError("conversation_title_version_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIAnswerError("answer_budget_denied")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    user_payload = {
        "user_excerpt": user_excerpt,
        "assistant_excerpt": assistant_excerpt,
    }
    try:
        response = client.responses.create(
            model=model_id,
            instructions=prompt_text,
            input=json.dumps(user_payload, separators=(",", ":")),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "conversation_title",
                    "strict": True,
                    "schema": conversation_title_json_schema(),
                }
            },
            max_output_tokens=CONVERSATION_TITLE_MAX_OUTPUT_TOKENS,
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
    return _parse_conversation_title_response(response)


def _parse_conversation_title_response(
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
        raise OpenAIAnswerError("conversation_title_incomplete")
    usage = getattr(response, "usage", None)
    if usage is None:
        raise OpenAIAnswerError("conversation_title_unknown_usage")
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    text = getattr(response, "output_text", "") or ""
    if not str(text).strip():
        raise OpenAIAnswerError("conversation_title_incomplete")
    try:
        loaded: object = json.loads(str(text))
    except json.JSONDecodeError as error:
        raise OpenAIAnswerError("conversation_title_schema_invalid") from error
    if not isinstance(loaded, dict):
        raise OpenAIAnswerError("conversation_title_schema_invalid")
    parsed = cast(dict[str, object], loaded)
    title = parsed.get("title")
    if not isinstance(title, str) or not title.strip():
        raise OpenAIAnswerError("conversation_title_schema_invalid")
    return parsed, request_id, input_tokens, output_tokens
