"""OpenAI Responses rerank adapter. One operation, no tools, no SDK retries."""

from __future__ import annotations

import json
from typing import cast

from openai import APIStatusError, APITimeoutError, AuthenticationError

from smart_rag_core.observability.langsmith_tracing import (
    rerank_responses_traceable,
    traced_openai_client,
)
from smart_rag_core.retrieval.profiles import (
    ALLOWED_RERANK_MODEL_IDS,
    RERANK_MAX_OUTPUT_TOKENS,
    RERANK_MODEL_ID,
)
from smart_rag_core.retrieval.rerank_labels import (
    rerank_label_json_schema,
    rerank_labels,
)
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)


class OpenAIRerankError(RuntimeError):
    """Typed provider failure for one rerank Responses call."""

    def __init__(self, reason: str) -> None:
        """Store a machine-readable fallback reason.

        Args:
            reason: ``RerankFallbackReason`` value.
        """

        super().__init__(reason)
        self.reason = reason


@rerank_responses_traceable
def execute_openai_rerank(
    *,
    api_key: str,
    prompt_text: str,
    prompt_sha256: str,
    prompt_version: str,
    model_id: str,
    query: str,
    candidate_ids: tuple[str, ...],
    excerpts: tuple[str, ...],
    input_hash: str,
    timeout_seconds: float,
) -> tuple[dict[str, object], str, int, int]:
    """Make exactly one structured Responses call.

    Args:
        api_key: Provider credential. Never logged.
        prompt_text: Pinned rerank prompt body.
        prompt_sha256: Expected prompt digest.
        prompt_version: Expected prompt version.
        model_id: Allow-listed model.
        query: Original query.
        candidate_ids: Pool IDs. Only their count reaches the model, as labels.
        excerpts: Canonical excerpts aligned with IDs and labels.
        input_hash: Canonical request hash. Traced for audit; never sent to the model.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Parsed JSON payload, provider request id, input tokens, output tokens.

    Raises:
        OpenAIRerankError: Timeout, auth, HTTP, version, or parse failures.
        ValueError: If versions or the model id are not allow-listed.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. No tools. When
        LangSmith tracing is enabled, a redacted ``openai.responses.rerank``
        span is exported.
    """

    if prompt_version != RERANK_PROMPT_VERSION or prompt_sha256 != RERANK_PROMPT_SHA256:
        raise OpenAIRerankError("rerank_version_mismatch")
    if model_id not in ALLOWED_RERANK_MODEL_IDS:
        raise OpenAIRerankError("rerank_version_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIRerankError("rerank_budget_denied")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    labels = rerank_labels(len(candidate_ids))
    schema = rerank_label_json_schema(labels)
    user_payload = {
        "query": query,
        "candidates": [
            {"label": label, "excerpt": excerpt}
            for label, excerpt in zip(labels, excerpts, strict=True)
        ],
    }
    try:
        response = client.responses.create(
            model=model_id,
            instructions=prompt_text,
            input=json.dumps(user_payload, separators=(",", ":")),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "hybrid_rerank",
                    "strict": True,
                    "schema": schema,
                }
            },
            max_output_tokens=RERANK_MAX_OUTPUT_TOKENS,
            store=False,
        )
    except APITimeoutError as error:
        raise OpenAIRerankError("rerank_timeout") from error
    except AuthenticationError as error:
        raise OpenAIRerankError("rerank_provider_error") from error
    except APIStatusError as error:
        if error.status_code == 429:
            raise OpenAIRerankError("rerank_budget_denied") from error
        raise OpenAIRerankError("rerank_provider_error") from error
    request_id = str(getattr(response, "id", "") or "unknown")
    status = getattr(response, "status", None)
    if status not in {None, "completed"}:
        raise OpenAIRerankError("rerank_incomplete")
    usage = getattr(response, "usage", None)
    if usage is None:
        raise OpenAIRerankError("rerank_unknown_usage")
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    text = getattr(response, "output_text", "") or ""
    if not text.strip():
        raise OpenAIRerankError("rerank_incomplete")
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise OpenAIRerankError("rerank_schema_invalid") from error
    if not isinstance(loaded, dict):
        raise OpenAIRerankError("rerank_schema_invalid")
    payload = cast(dict[str, object], loaded)
    return payload, request_id, input_tokens, output_tokens


def default_rerank_model() -> str:
    """Return the Packet 5 allow-listed rerank model id.

    Returns:
        ``gpt-4o-mini``.
    """

    return RERANK_MODEL_ID
