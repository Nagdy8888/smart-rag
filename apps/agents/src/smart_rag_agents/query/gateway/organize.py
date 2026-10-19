"""One counted rewrite of an already verified company answer."""

from __future__ import annotations

from typing import Any, cast

from smart_rag_core.gateways.model import AnswerModelRequest
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.versions import (
    ORGANIZE_PROMPT_SHA256,
    ORGANIZE_PROMPT_VERSION,
)

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    attempt_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.answer_attempts import ANSWER_ATTEMPT_CAP_SECONDS
from smart_rag_agents.query.nodes.tokens import tokens_from_gateway_response


def gateway_organize(
    deps: QueryGraphDeps,
    *,
    query: str,
    verified_text: str,
    context: AuthorizedRuntimeContext | None,
) -> tuple[str, int, int]:
    """Ask the model to rewrite verified claims into one titled answer.

    The provider still returns the claims schema. Only the first claim
    text is kept. Citations on that claim are ignored.

    Args:
        deps: Bound gateway and organize prompt.
        query: Original user question. Untrusted.
        verified_text: Claims that already passed verification.
        context: Admitted run context used for the live deadline timeout.

    Returns:
        Rewritten answer text plus provider prompt and completion tokens.

    Raises:
        AnswerError: If the gateway is unbound or the payload has no claim.
    """

    gateway = deps.model_gateway
    prompt = str(deps.organize_prompt_text or "").strip()
    if gateway is None or not prompt:
        raise AnswerError("model_gateway_unbound")
    timeout_seconds = attempt_timeout_seconds(context, ANSWER_ATTEMPT_CAP_SECONDS)
    request = AnswerModelRequest(
        query=(query or "query")[:2000],
        prompt_version=ORGANIZE_PROMPT_VERSION,
        prompt_sha256=ORGANIZE_PROMPT_SHA256,
        prompt_text=prompt[:16_384],
        source_records=verified_text[:65_536] or " ",
        remaining_deadline_seconds=timeout_seconds,
    )
    response = cast(
        Any,
        run_coro(
            lambda: cast(Any, gateway).generate_answer(request),
            cancel_check=deps.cancel_check,
            timeout_seconds=request.remaining_deadline_seconds,
        ),
    )
    text = _first_claim_text(getattr(response, "payload", None))
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return text, prompt_tokens, completion_tokens


def _first_claim_text(payload: object) -> str:
    """Return the first claim body without collapsing its newlines.

    Args:
        payload: Provider JSON object.

    Returns:
        Claim text.

    Raises:
        AnswerError: When the payload is not a claims object.
    """

    if not isinstance(payload, dict):
        raise AnswerError("organize_schema_invalid")
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        raise AnswerError("organize_schema_invalid")
    first = claims[0]
    if not isinstance(first, dict):
        raise AnswerError("organize_schema_invalid")
    text = first.get("text")
    if not isinstance(text, str) or not text.strip():
        raise AnswerError("organize_schema_invalid")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()
