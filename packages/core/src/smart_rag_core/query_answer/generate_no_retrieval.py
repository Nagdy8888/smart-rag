"""Deterministic, general, user-text, and clarification generation."""

from __future__ import annotations

from collections.abc import Callable

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.sanitize import (
    apply_degraded_scope_framing,
    empty_no_retrieval,
    sanitize_general_chat_payload,
)
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    NoRetrievalAnswerMode,
    ScopeDegradationReason,
)
from smart_rag_core.query_routing.signals import (
    is_greeting,
    is_product_help,
    is_user_text_transform,
)

GeneralChatCaller = Callable[[str, str, KnowledgeScope], AnswerPayload]

GREETING_TEXT = (
    "Hi! I'm ready to help. Ask me a question about your uploaded "
    "documents, and I'll answer from the authorized evidence."
)
CLARIFICATION_TEXT = (
    "This question mixes general knowledge and company documents. "
    "Ask one general question or one document question so the answer source stays clear."
)


def generate_no_retrieval(
    *,
    user_query: str,
    knowledge_scope: KnowledgeScope | None,
    no_retrieval_answer_mode: NoRetrievalAnswerMode | None,
    general_caller: GeneralChatCaller | None,
    recent_memory: str,
    scope_degradation_reason: ScopeDegradationReason | None,
) -> AnswerPayload:
    """Answer a NoRetrieval query without citations or document claims.

    Args:
        user_query: Original user text.
        knowledge_scope: Routed scope, when known.
        no_retrieval_answer_mode: Routed mode, when known.
        general_caller: Optional live/mock general-chat adapter.
        recent_memory: Delimited untrusted memory.
        scope_degradation_reason: Failed-profile reason, when present.

    Returns:
        Uncited greeting, clarification, general, or user-text payload.
        ``DETERMINISTIC_CHAT`` is answered by the general model, not canned
        greeting text.
    """

    mode = resolve_no_retrieval_mode(
        user_query, no_retrieval_answer_mode, knowledge_scope
    )
    if mode is NoRetrievalAnswerMode.DETERMINISTIC_CHAT:
        mode = NoRetrievalAnswerMode.GENERAL_MODEL
    if mode is NoRetrievalAnswerMode.CLARIFICATION:
        return empty_no_retrieval(
            CLARIFICATION_TEXT,
            status="complete",
            origin=KnowledgeScope.AMBIGUOUS,
        )
    if mode in {
        NoRetrievalAnswerMode.GENERAL_MODEL,
        NoRetrievalAnswerMode.USER_TEXT_MODEL,
    }:
        origin = (
            KnowledgeScope.USER_SUPPLIED_TEXT
            if mode is NoRetrievalAnswerMode.USER_TEXT_MODEL
            else KnowledgeScope.GENERAL_KNOWLEDGE
        )
        if general_caller is None:
            payload = mock_general_chat_payload(
                user_query, recent_memory=recent_memory, knowledge_scope=origin
            )
        else:
            payload = general_caller(user_query, recent_memory, origin)
        sanitized = sanitize_general_chat_payload(payload, origin=origin)
        return apply_degraded_scope_framing(
            sanitized, scope_degradation_reason=scope_degradation_reason
        )
    return empty_no_retrieval(
        "No company-knowledge claim is authorized for this query.",
        status="refused",
        origin=knowledge_scope,
    )


def resolve_no_retrieval_mode(
    user_query: str,
    mode: NoRetrievalAnswerMode | None,
    knowledge_scope: KnowledgeScope | None,
) -> NoRetrievalAnswerMode | None:
    """Resolve a NoRetrieval mode from routing or local signals.

    Args:
        user_query: Original user text.
        mode: Routed mode.
        knowledge_scope: Routed scope.

    Returns:
        Concrete mode, or None when the query must refuse.
    """

    if mode is not None:
        return mode
    if knowledge_scope is KnowledgeScope.DETERMINISTIC:
        return NoRetrievalAnswerMode.GENERAL_MODEL
    if knowledge_scope is KnowledgeScope.AMBIGUOUS:
        return NoRetrievalAnswerMode.CLARIFICATION
    if knowledge_scope is KnowledgeScope.USER_SUPPLIED_TEXT or is_user_text_transform(
        user_query
    ):
        return NoRetrievalAnswerMode.USER_TEXT_MODEL
    if (
        knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
        or is_greeting(user_query)
        or is_product_help(user_query)
    ):
        return NoRetrievalAnswerMode.GENERAL_MODEL
    return None


def mock_general_chat_payload(
    user_query: str,
    *,
    recent_memory: str,
    knowledge_scope: KnowledgeScope,
) -> AnswerPayload:
    """Build a deterministic no-network general-chat fixture.

    Args:
        user_query: Original user text.
        recent_memory: Unused delimited memory. Kept for the live contract.
        knowledge_scope: General or user-text origin.

    Returns:
        Uncited complete answer. No DNS or provider call.
    """

    del recent_memory
    if knowledge_scope is KnowledgeScope.USER_SUPPLIED_TEXT:
        supplied = user_query.split(":", 1)[-1].strip() or user_query.strip()
        text = f"Rewritten user text: {supplied}"
    elif is_product_help(user_query):
        text = (
            "I can answer general questions from model knowledge, rewrite text "
            "you paste, or answer from your authorized company documents with "
            "citations when you ask a document-scoped question."
        )
    elif "capital of france" in user_query.casefold():
        text = "Paris is the capital of France."
    else:
        text = (
            "Here is a general answer from model knowledge, not from your "
            "company documents."
        )
    return AnswerPayload(
        answer_text=text,
        status="complete",
        answer_origin=knowledge_scope,
    )
