"""Public dispatcher for one counted answer generation."""

from __future__ import annotations

from collections.abc import Callable

from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.generate_grounded import (
    generate_grounded_answer,
    mock_answer_payload,
)
from smart_rag_core.query_answer.generate_no_retrieval import (
    CLARIFICATION_TEXT,
    GREETING_TEXT,
    generate_no_retrieval,
    mock_general_chat_payload,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.sanitize import (
    DEGRADED_NO_COMPANY_SEARCH,
    GENERAL_DOCUMENT_REFUSAL,
    apply_degraded_scope_framing,
    claims_document_access,
    filter_invented_ids,
    sanitize_general_chat_payload,
)
from smart_rag_core.query_answer.versions import MAX_ANSWER_GENERATIONS
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    NoRetrievalAnswerMode,
    ScopeDegradationReason,
)
from smart_rag_core.query_routing.models import TableEvidenceRecord

AnswerCaller = Callable[
    [str, FusionResult, tuple[TableEvidenceRecord, ...]], AnswerPayload
]
GeneralChatCaller = Callable[[str, str, KnowledgeScope], AnswerPayload]

__all__ = [
    "CLARIFICATION_TEXT",
    "DEGRADED_NO_COMPANY_SEARCH",
    "GENERAL_DOCUMENT_REFUSAL",
    "GREETING_TEXT",
    "AnswerCaller",
    "GeneralChatCaller",
    "apply_degraded_scope_framing",
    "claims_document_access",
    "filter_invented_ids",
    "generate_answer",
    "mock_answer_payload",
    "mock_general_chat_payload",
    "sanitize_general_chat_payload",
]


def generate_answer(
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    user_query: str,
    caller: AnswerCaller | None,
    already_generated: int,
    company_claim_forbidden: bool,
    graph_as_answer_forbidden: bool,
    knowledge_scope: KnowledgeScope | None = None,
    no_retrieval_answer_mode: NoRetrievalAnswerMode | None = None,
    general_caller: GeneralChatCaller | None = None,
    recent_memory: str = "",
    scope_degradation_reason: ScopeDegradationReason | None = None,
) -> AnswerPayload:
    """Generate one evidence answer or a scoped no-retrieval response.

    Args:
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text. Untrusted.
        caller: Structured RAG answer adapter. None uses the extractive mock.
        already_generated: Existing answer count. A second call fails.
        company_claim_forbidden: True for NoRetrieval.
        graph_as_answer_forbidden: True for graph-only inspection.
        knowledge_scope: Strict-split origin from routing, when known.
        no_retrieval_answer_mode: NoRetrieval answer mode, when known.
        general_caller: One general-chat adapter. None uses the mock.
        recent_memory: Delimited untrusted conversation memory.
        scope_degradation_reason: Server-derived failed-profile reason.
            Adds explicit no-company-search framing on the general path.

    Returns:
        Structured answer. Document paths still pass ``filter_invented_ids``.
        No-retrieval outputs have empty citations and no company claims.

    Raises:
        AnswerError: A second answer generation was requested.
    """

    if already_generated >= MAX_ANSWER_GENERATIONS:
        raise AnswerError("second_answer_generation")
    if graph_as_answer_forbidden:
        return AnswerPayload(
            answer_text="Graph inspection cannot answer from graph leads.",
            status="refused",
        )
    if knowledge_scope is KnowledgeScope.WEB:
        return AnswerPayload(
            answer_text="Web research is not bound on this run.",
            status="refused",
            answer_origin=KnowledgeScope.WEB,
        )
    if company_claim_forbidden or knowledge_scope in {
        KnowledgeScope.GENERAL_KNOWLEDGE,
        KnowledgeScope.USER_SUPPLIED_TEXT,
        KnowledgeScope.DETERMINISTIC,
        KnowledgeScope.AMBIGUOUS,
    }:
        return generate_no_retrieval(
            user_query=user_query,
            knowledge_scope=knowledge_scope,
            no_retrieval_answer_mode=no_retrieval_answer_mode,
            general_caller=general_caller,
            recent_memory=recent_memory,
            scope_degradation_reason=scope_degradation_reason,
        )
    return generate_grounded_answer(
        fusion=fusion,
        tables=tables,
        user_query=user_query,
        caller=caller,
    )
