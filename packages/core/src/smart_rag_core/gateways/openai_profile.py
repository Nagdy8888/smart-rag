"""OpenAI Responses adapter for one structured query-profile call."""

from __future__ import annotations

import json
from typing import cast

from openai import APIStatusError, APITimeoutError, AuthenticationError
from pydantic import ValidationError

from smart_rag_core.gateways.provider_usage import observe_provider_response
from smart_rag_core.observability.langsmith_tracing import (
    query_profile_responses_traceable,
    traced_openai_client,
)
from smart_rag_core.query_profile.schemas import query_profile_json_schema
from smart_rag_core.query_profile.versions import (
    ALLOWED_PROFILE_MODEL_IDS,
    PROFILE_MAX_OUTPUT_TOKENS,
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.query_routing.models import PreparationModelPayload


class OpenAIProfileError(RuntimeError):
    """Typed provider failure for one query-profile Responses call.

    Attributes:
        reason: Short machine-readable code.
    """

    def __init__(self, reason: str) -> None:
        """Store a machine-readable fallback reason.

        Args:
            reason: Short reason code.
        """

        super().__init__(reason)
        self.reason = reason


@query_profile_responses_traceable
def execute_openai_query_profile(
    *,
    api_key: str,
    prompt_text: str,
    prompt_sha256: str,
    prompt_version: str,
    model_id: str,
    user_query: str,
    recent_memory: str,
    timeout_seconds: float,
) -> tuple[dict[str, object], str, int, int]:
    """Make exactly one structured query-profile Responses call.

    Args:
        api_key: Provider credential. Never logged.
        prompt_text: Pinned profile prompt body.
        prompt_sha256: Expected prompt digest.
        prompt_version: Expected prompt version.
        model_id: Allow-listed profile model. No new model name.
        user_query: Original user text.
        recent_memory: Delimited untrusted conversation memory.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Parsed JSON payload, provider request id, input tokens, output tokens.

    Raises:
        OpenAIProfileError: Timeout, auth, HTTP, version, or parse failures.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. ``store=False``.
        No tools or retrieval. When LangSmith tracing is enabled, a redacted
        ``openai.responses.query_profile`` span is exported.
    """

    if (
        prompt_version != PROFILE_PROMPT_VERSION
        or prompt_sha256 != PROFILE_PROMPT_SHA256
    ):
        raise OpenAIProfileError("profile_version_mismatch")
    if model_id not in ALLOWED_PROFILE_MODEL_IDS:
        raise OpenAIProfileError("profile_version_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIProfileError("profile_budget_denied")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    user_payload = {
        "query": user_query,
        "memory": recent_memory,
    }
    try:
        response = client.responses.create(
            model=model_id,
            instructions=prompt_text,
            input=json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "query_profile",
                    "strict": True,
                    "schema": query_profile_json_schema(),
                }
            },
            max_output_tokens=PROFILE_MAX_OUTPUT_TOKENS,
            store=False,
        )
    except APITimeoutError as error:
        raise OpenAIProfileError("profile_timeout") from error
    except AuthenticationError as error:
        raise OpenAIProfileError("profile_provider_error") from error
    except APIStatusError as error:
        if error.status_code == 429:
            raise OpenAIProfileError("profile_budget_denied") from error
        raise OpenAIProfileError("profile_provider_error") from error
    return _parse_query_profile_response(response)


def _parse_query_profile_response(
    response: object,
) -> tuple[dict[str, object], str, int, int]:
    """Parse one Responses object into JSON plus usage.

    Args:
        response: Provider response.

    Returns:
        Payload, request id, input tokens, output tokens.

    Raises:
        OpenAIProfileError: Incomplete or invalid JSON.
    """

    observe_provider_response(response)
    request_id = str(getattr(response, "id", "") or "unknown")
    status = getattr(response, "status", None)
    if status not in {None, "completed"}:
        raise OpenAIProfileError("profile_incomplete")
    usage = getattr(response, "usage", None)
    if usage is None or any(
        type(getattr(usage, field, None)) is not int or getattr(usage, field) < 0
        for field in ("input_tokens", "output_tokens")
    ):
        raise OpenAIProfileError("profile_unknown_usage")
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    text = getattr(response, "output_text", "") or ""
    if not str(text).strip():
        raise OpenAIProfileError("profile_incomplete")
    try:
        loaded: object = json.loads(str(text))
    except json.JSONDecodeError as error:
        raise OpenAIProfileError("profile_schema_invalid") from error
    if not isinstance(loaded, dict):
        raise OpenAIProfileError("profile_schema_invalid")
    raw = cast(dict[str, object], loaded)
    if "scope_degradation_reason" in raw:
        raise OpenAIProfileError("profile_schema_invalid")
    try:
        payload = PreparationModelPayload.model_validate(raw)
    except ValidationError as error:
        raise OpenAIProfileError("profile_schema_invalid") from error
    return payload.model_dump(mode="json"), request_id, input_tokens, output_tokens
