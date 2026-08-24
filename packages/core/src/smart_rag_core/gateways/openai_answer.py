"""OpenAI Responses adapters for one answer call and one verifier call."""

from __future__ import annotations

import json
from typing import cast

from openai import APIStatusError, APITimeoutError, AuthenticationError

from smart_rag_core.observability.langsmith_tracing import traced_openai_client
from smart_rag_core.query_answer.schemas import (
    answer_json_schema,
    eval_judge_json_schema,
    verifier_json_schema,
)
from smart_rag_core.query_answer.versions import (
    ALLOWED_ANSWER_MODEL_IDS,
    ALLOWED_EVAL_JUDGE_MODEL_IDS,
    ALLOWED_VERIFIER_MODEL_IDS,
    ANSWER_MAX_OUTPUT_TOKENS,
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    EVAL_JUDGE_MAX_OUTPUT_TOKENS,
    EVAL_JUDGE_PROMPT_SHA256,
    EVAL_JUDGE_PROMPT_VERSION,
    VERIFIER_MAX_OUTPUT_TOKENS,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)


class OpenAIAnswerError(RuntimeError):
    """Typed provider failure for one answer or verifier Responses call."""

    def __init__(self, reason: str) -> None:
        """Store a machine-readable fallback reason.

        Args:
            reason: Short reason code.
        """

        super().__init__(reason)
        self.reason = reason


def execute_openai_answer(
    *,
    api_key: str,
    prompt_text: str,
    prompt_sha256: str,
    prompt_version: str,
    model_id: str,
    user_query: str,
    source_records: str,
    timeout_seconds: float,
) -> tuple[dict[str, object], str, int, int]:
    """Make exactly one structured answer Responses call.

    Args:
        api_key: Provider credential. Never logged.
        prompt_text: Pinned answer prompt body.
        prompt_sha256: Expected prompt digest.
        prompt_version: Expected prompt version.
        model_id: Allow-listed model.
        user_query: Original user text.
        source_records: Delimited untrusted source records.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Parsed JSON payload, provider request id, input tokens, output tokens.

    Raises:
        OpenAIAnswerError: Timeout, auth, HTTP, version, or parse failures.
        ValueError: If versions or the model id are not allow-listed.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. No tools.
    """

    if prompt_version != ANSWER_PROMPT_VERSION or prompt_sha256 != ANSWER_PROMPT_SHA256:
        raise OpenAIAnswerError("answer_version_mismatch")
    if model_id not in ALLOWED_ANSWER_MODEL_IDS:
        raise OpenAIAnswerError("answer_version_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIAnswerError("answer_budget_denied")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    user_payload = {"query": user_query, "sources": source_records}
    try:
        response = client.responses.create(
            model=model_id,
            instructions=prompt_text,
            input=json.dumps(user_payload, separators=(",", ":")),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "canonical_answer",
                    "strict": True,
                    "schema": answer_json_schema(),
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
    return _parse_response(response, kind="answer")


def execute_openai_verifier(
    *,
    api_key: str,
    prompt_text: str,
    prompt_sha256: str,
    prompt_version: str,
    model_id: str,
    source_records: str,
    link_payload: list[dict[str, object]],
    link_ids: tuple[str, ...],
    timeout_seconds: float,
) -> tuple[dict[str, object], str, int, int]:
    """Make exactly one structured verifier Responses call.

    Args:
        api_key: Provider credential. Never logged.
        prompt_text: Pinned verifier prompt body.
        prompt_sha256: Expected prompt digest.
        prompt_version: Expected prompt version.
        model_id: Allow-listed small model.
        source_records: Delimited untrusted source records.
        link_payload: At most six atomic links.
        link_ids: Link IDs bound into the JSON schema enum.
        timeout_seconds: Client timeout.

    Returns:
        Parsed JSON payload, provider request id, input tokens, output tokens.

    Raises:
        OpenAIAnswerError: Provider or schema failures.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. No tools.
    """

    if (
        prompt_version != VERIFIER_PROMPT_VERSION
        or prompt_sha256 != VERIFIER_PROMPT_SHA256
    ):
        raise OpenAIAnswerError("verifier_version_mismatch")
    if model_id not in ALLOWED_VERIFIER_MODEL_IDS:
        raise OpenAIAnswerError("verifier_version_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIAnswerError("verifier_budget_denied")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    user_payload = {"sources": source_records, "links": link_payload}
    try:
        response = client.responses.create(
            model=model_id,
            instructions=prompt_text,
            input=json.dumps(user_payload, separators=(",", ":")),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "atomic_link_verifier",
                    "strict": True,
                    "schema": verifier_json_schema(link_ids),
                }
            },
            max_output_tokens=VERIFIER_MAX_OUTPUT_TOKENS,
            store=False,
        )
    except APITimeoutError as error:
        raise OpenAIAnswerError("verifier_timeout") from error
    except AuthenticationError as error:
        raise OpenAIAnswerError("verifier_provider_error") from error
    except APIStatusError as error:
        if error.status_code == 429:
            raise OpenAIAnswerError("verifier_budget_denied") from error
        raise OpenAIAnswerError("verifier_provider_error") from error
    return _parse_response(response, kind="verifier")


def execute_openai_eval_judge(
    *,
    api_key: str,
    prompt_text: str,
    prompt_sha256: str,
    prompt_version: str,
    model_id: str,
    user_payload: dict[str, object],
    timeout_seconds: float,
) -> tuple[dict[str, object], str, int, int]:
    """Make exactly one structured synthetic-eval judge Responses call.

    Args:
        api_key: Provider credential. Never logged.
        prompt_text: Pinned judge prompt body.
        prompt_sha256: Expected prompt digest.
        prompt_version: Expected prompt version.
        model_id: Allow-listed small model.
        user_payload: Synthetic question, answers, and bounded evidence ids.
        timeout_seconds: Client timeout. SDK retries are disabled.

    Returns:
        Parsed JSON payload, provider request id, input tokens, output tokens.

    Raises:
        OpenAIAnswerError: Timeout, auth, HTTP, version, or parse failures.

    Side Effects:
        One HTTPS Responses request. ``max_retries=0``. No tools.
    """

    if (
        prompt_version != EVAL_JUDGE_PROMPT_VERSION
        or prompt_sha256 != EVAL_JUDGE_PROMPT_SHA256
    ):
        raise OpenAIAnswerError("eval_judge_version_mismatch")
    if model_id not in ALLOWED_EVAL_JUDGE_MODEL_IDS:
        raise OpenAIAnswerError("eval_judge_version_mismatch")
    if timeout_seconds <= 0:
        raise OpenAIAnswerError("eval_judge_budget_denied")
    client = traced_openai_client(
        api_key=api_key, max_retries=0, timeout=timeout_seconds
    )
    try:
        response = client.responses.create(
            model=model_id,
            instructions=prompt_text,
            input=json.dumps(user_payload, separators=(",", ":")),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "synthetic_eval_judge",
                    "strict": True,
                    "schema": eval_judge_json_schema(),
                }
            },
            max_output_tokens=EVAL_JUDGE_MAX_OUTPUT_TOKENS,
            store=False,
        )
    except APITimeoutError as error:
        raise OpenAIAnswerError("eval_judge_timeout") from error
    except AuthenticationError as error:
        raise OpenAIAnswerError("eval_judge_provider_error") from error
    except APIStatusError as error:
        if error.status_code == 429:
            raise OpenAIAnswerError("eval_judge_budget_denied") from error
        raise OpenAIAnswerError("eval_judge_provider_error") from error
    return _parse_response(response, kind="eval_judge")


def _parse_response(
    response: object,
    *,
    kind: str,
) -> tuple[dict[str, object], str, int, int]:
    """Parse one Responses object into JSON plus usage.

    Args:
        response: Provider response.
        kind: ``answer`` or ``verifier`` for error prefixes.

    Returns:
        Payload, request id, input tokens, output tokens.

    Raises:
        OpenAIAnswerError: Incomplete or invalid JSON.
    """

    request_id = str(getattr(response, "id", "") or "unknown")
    status = getattr(response, "status", None)
    if status not in {None, "completed"}:
        raise OpenAIAnswerError(f"{kind}_incomplete")
    usage = getattr(response, "usage", None)
    if usage is None:
        raise OpenAIAnswerError(f"{kind}_unknown_usage")
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    text = getattr(response, "output_text", "") or ""
    if not text.strip():
        raise OpenAIAnswerError(f"{kind}_incomplete")
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise OpenAIAnswerError(f"{kind}_schema_invalid") from error
    if not isinstance(loaded, dict):
        raise OpenAIAnswerError(f"{kind}_schema_invalid")
    return cast(dict[str, object], loaded), request_id, input_tokens, output_tokens
