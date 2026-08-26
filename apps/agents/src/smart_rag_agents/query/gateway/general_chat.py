"""Counted general-chat gateway bridge."""

from __future__ import annotations

from typing import Any, Literal, cast

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate import sanitize_general_chat_payload
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.versions import (
    GENERAL_CHAT_PROMPT_SHA256,
    GENERAL_CHAT_PROMPT_VERSION,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import (
    gateway_timeout_seconds,
    run_coro,
)
from smart_rag_agents.query.nodes.tokens import tokens_from_gateway_response


def gateway_general_chat(
    deps: QueryGraphDeps,
    *,
    query: str,
    knowledge_scope: KnowledgeScope,
    recent_memory: str,
    context: AuthorizedRuntimeContext | None,
) -> tuple[AnswerPayload, int, int]:
    """Run one async general-chat gateway call from the sync graph.

    Args:
        deps: Bound gateway and general-chat prompt.
        query: User query.
        knowledge_scope: General or user-text origin.
        recent_memory: Delimited untrusted memory.
        context: Admitted run context used for the live deadline timeout.

    Returns:
        Parsed uncited answer payload plus provider token counts.

    Raises:
        AnswerError: If the gateway is unbound or the provider fails.
    """

    from smart_rag_core.gateways.model import GeneralChatModelRequest

    timeout_seconds = gateway_timeout_seconds(context)
    request = GeneralChatModelRequest(
        query=query or "query",
        recent_memory=recent_memory,
        knowledge_scope=knowledge_scope,
        prompt_version=GENERAL_CHAT_PROMPT_VERSION,
        prompt_sha256=GENERAL_CHAT_PROMPT_SHA256,
        prompt_text=str(deps.general_chat_prompt_text or "general_chat"),
        remaining_deadline_seconds=timeout_seconds,
    )
    gateway = deps.model_gateway
    if gateway is None:
        raise AnswerError("model_gateway_unbound")
    try:
        response = cast(
            Any,
            run_coro(
                lambda: cast(Any, gateway).generate_general_chat(request),
                cancel_check=deps.cancel_check,
                timeout_seconds=request.remaining_deadline_seconds,
            ),
        )
    except AnswerError:
        raise
    except Exception as exc:
        raise AnswerError("general_chat_provider_error") from exc
    raw_payload: object = getattr(response, "payload", {})
    if not isinstance(raw_payload, dict):
        raise AnswerError("general_chat_schema_invalid")
    typed_raw = {
        str(key): value
        for key, value in cast(dict[object, object], raw_payload).items()
    }
    raw_status = typed_raw.get("status")
    status: Literal["complete", "partial", "refused"] = "refused"
    if raw_status == "complete":
        status = "complete"
    elif raw_status == "partial":
        status = "partial"
    payload = AnswerPayload(
        answer_text=str(typed_raw.get("answer_text") or ""),
        status=status,
        answer_origin=knowledge_scope,
    )
    prompt_tokens, completion_tokens = tokens_from_gateway_response(response)
    return (
        sanitize_general_chat_payload(payload, origin=knowledge_scope),
        prompt_tokens,
        completion_tokens,
    )
