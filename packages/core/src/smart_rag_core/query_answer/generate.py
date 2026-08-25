"""One counted answer generation from canonical passages and table values."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal

from smart_rag_core.query_answer.assembly import (
    allowed_chunk_ids,
    allowed_table_ids,
    assemble_source_records,
)
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
)
from smart_rag_core.query_answer.versions import MAX_ANSWER_GENERATIONS
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    NoRetrievalAnswerMode,
)
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.query_routing.signals import (
    is_greeting,
    is_product_help,
    is_user_text_transform,
)

AnswerCaller = Callable[
    [str, FusionResult, tuple[TableEvidenceRecord, ...]], AnswerPayload
]
GeneralChatCaller = Callable[[str, str, KnowledgeScope], AnswerPayload]

GREETING_TEXT = (
    "Hi! I'm ready to help. Ask me a question about your uploaded "
    "documents, and I'll answer from the authorized evidence."
)
CLARIFICATION_TEXT = (
    "This question mixes general knowledge and company documents. "
    "Ask one general question or one document question so the answer source stays clear."
)
GENERAL_DOCUMENT_REFUSAL = (
    "I can answer general questions from model knowledge, but I cannot claim "
    "to have searched company documents on this path. Ask a document-scoped "
    "question for a cited answer."
)
_DOCUMENT_CLAIM_PHRASES = (
    "according to your documents",
    "i found in your files",
    "i searched your documents",
    "i opened your documents",
    "i read your documents",
    "based on your uploaded",
    "in your company documents",
    "from your company knowledge",
)
_SOURCE_ID_CLAIM = re.compile(
    r"(?i)\b(?:chunk|source|citation|p4-src|inv-sr|sku-p4)[-_:][a-z0-9-]+"
)


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
    if company_claim_forbidden or knowledge_scope in {
        KnowledgeScope.GENERAL_KNOWLEDGE,
        KnowledgeScope.USER_SUPPLIED_TEXT,
        KnowledgeScope.DETERMINISTIC,
        KnowledgeScope.AMBIGUOUS,
    }:
        return _generate_no_retrieval(
            user_query=user_query,
            knowledge_scope=knowledge_scope,
            no_retrieval_answer_mode=no_retrieval_answer_mode,
            general_caller=general_caller,
            recent_memory=recent_memory,
        )
    if not fusion.evidence and not tables:
        return _empty_no_retrieval(
            "Insufficient authorized evidence.",
            status="refused",
            origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )
    records = assemble_source_records(fusion, tables)
    if caller is None:
        payload = mock_answer_payload(fusion, tables, user_query=user_query)
    else:
        payload = caller(records, fusion, tables)
    filtered = filter_invented_ids(payload, fusion, tables)
    return filtered.model_copy(
        update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
    )


def _generate_no_retrieval(
    *,
    user_query: str,
    knowledge_scope: KnowledgeScope | None,
    no_retrieval_answer_mode: NoRetrievalAnswerMode | None,
    general_caller: GeneralChatCaller | None,
    recent_memory: str,
) -> AnswerPayload:
    """Answer a NoRetrieval query without citations or document claims.

    Args:
        user_query: Original user text.
        knowledge_scope: Routed scope, when known.
        no_retrieval_answer_mode: Routed mode, when known.
        general_caller: Optional live/mock general-chat adapter.
        recent_memory: Delimited untrusted memory.

    Returns:
        Uncited greeting, clarification, general, or user-text payload.
    """

    mode = _resolve_no_retrieval_mode(
        user_query, no_retrieval_answer_mode, knowledge_scope
    )
    if mode is NoRetrievalAnswerMode.DETERMINISTIC_CHAT:
        return _empty_no_retrieval(
            GREETING_TEXT,
            status="complete",
            origin=KnowledgeScope.DETERMINISTIC,
        )
    if mode is NoRetrievalAnswerMode.CLARIFICATION:
        return _empty_no_retrieval(
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
        return sanitize_general_chat_payload(payload, origin=origin)
    return _empty_no_retrieval(
        "No company-knowledge claim is authorized for this query.",
        status="refused",
        origin=knowledge_scope,
    )


def _resolve_no_retrieval_mode(
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
        return NoRetrievalAnswerMode.DETERMINISTIC_CHAT
    if knowledge_scope is KnowledgeScope.AMBIGUOUS:
        return NoRetrievalAnswerMode.CLARIFICATION
    if (
        knowledge_scope is KnowledgeScope.USER_SUPPLIED_TEXT
        or is_user_text_transform(user_query)
    ):
        return NoRetrievalAnswerMode.USER_TEXT_MODEL
    if (
        knowledge_scope is KnowledgeScope.GENERAL_KNOWLEDGE
        or is_greeting(user_query)
        or is_product_help(user_query)
    ):
        return NoRetrievalAnswerMode.GENERAL_MODEL
    return None


def _empty_no_retrieval(
    text: str,
    *,
    status: Literal["complete", "partial", "refused"],
    origin: KnowledgeScope | None,
) -> AnswerPayload:
    """Build an uncited no-retrieval payload.

    Args:
        text: Answer prose.
        status: ``complete``, ``partial``, or ``refused``.
        origin: Strict-split origin, or None.

    Returns:
        Payload with empty citations, links, and table citations.
    """

    return AnswerPayload(
        answer_text=text,
        status=status,
        answer_origin=origin,
    )


def claims_document_access(text: str) -> bool:
    """Return whether general-chat prose claims company-document access.

    Args:
        text: Model or mock answer text.

    Returns:
        True when the text claims to have searched documents or emits IDs.
    """

    lowered = text.casefold()
    if any(phrase in lowered for phrase in _DOCUMENT_CLAIM_PHRASES):
        return True
    return _SOURCE_ID_CLAIM.search(text) is not None


def sanitize_general_chat_payload(
    payload: AnswerPayload, *, origin: KnowledgeScope
) -> AnswerPayload:
    """Drop citations and refuse document-access claims.

    Args:
        payload: General-chat model or mock result.
        origin: Intended no-retrieval origin.

    Returns:
        Uncited payload. Document-access claims become a safe refusal
        instead of a stripped success.
    """

    if claims_document_access(payload.answer_text):
        return _empty_no_retrieval(
            GENERAL_DOCUMENT_REFUSAL,
            status="refused",
            origin=origin,
        )
    return AnswerPayload(
        answer_text=payload.answer_text,
        status=payload.status,
        answer_origin=origin,
    )


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


def filter_invented_ids(
    payload: AnswerPayload,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Drop citations and links that invent IDs not in supplied evidence.

    Args:
        payload: Model or mock answer.
        fusion: Canonical evidence.
        tables: Table snapshots.

    Returns:
        Payload citing only supplied IDs. Citations with ``chunk_id is None``
        are dropped unless ``table_id`` is in allowed table IDs.
    """

    chunks = allowed_chunk_ids(fusion)
    table_ids = allowed_table_ids(tables)
    citations = tuple(
        item
        for item in payload.citations
        if _citation_has_allowed_source(item, chunks, table_ids)
    )
    table_citations = tuple(
        item
        for item in payload.table_citations
        if item.table_id is not None and item.table_id in table_ids
    )
    links = tuple(
        item.model_copy(
            update={
                "chunk_ids": tuple(
                    chunk_id for chunk_id in item.chunk_ids if chunk_id in chunks
                )
            }
        )
        for item in payload.atomic_links
        if (
            not item.chunk_ids or any(chunk_id in chunks for chunk_id in item.chunk_ids)
        )
        or (item.table_id is not None and item.table_id in table_ids)
    )
    return payload.model_copy(
        update={
            "citations": citations,
            "table_citations": table_citations,
            "atomic_links": links,
        }
    )


def _citation_has_allowed_source(
    item: AnswerCitation,
    chunks: frozenset[str],
    table_ids: frozenset[str],
) -> bool:
    """Return whether a citation names an allowed passage or table.

    Citations with ``chunk_id is None`` survive only when ``table_id`` is in
    supplied table IDs.

    Args:
        item: Candidate citation.
        chunks: Canonical chunk IDs from fusion.
        table_ids: Canonical table IDs from sandbox composition.

    Returns:
        True when the citation is grounded in supplied evidence.
    """

    if item.chunk_id is not None:
        return item.chunk_id in chunks
    return item.table_id is not None and item.table_id in table_ids


def mock_answer_payload(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    *,
    user_query: str,
) -> AnswerPayload:
    """Build a deterministic fixture answer that cites supplied evidence IDs.

    This is mock-mode output, not a live company-knowledge claim. Table
    values are copied, never recalculated from prose.

    Args:
        fusion: Canonical evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text.

    Returns:
        Structured answer citing every supplied passage and table range.
    """

    del user_query
    citations = tuple(
        AnswerCitation(
            chunk_id=item.chunk_id, span=None, atomic_link_id=f"link-{index}"
        )
        for index, item in enumerate(fusion.evidence, start=1)
    )
    table_citations = tuple(
        AnswerCitation(
            table_id=item.table_id,
            source_ranges=item.source_ranges,
            atomic_link_id=f"table-{index}",
        )
        for index, item in enumerate(tables, start=1)
    )
    links: list[AtomicLink] = [
        AtomicLink(
            link_id=f"link-{index}",
            claim=item.citation_text[:400] or f"Canonical passage {item.chunk_id}",
            chunk_ids=(item.chunk_id,),
            kind="inference_link" if item.statement_ids else "fact",
            priority=index,
        )
        for index, item in enumerate(fusion.evidence, start=1)
    ]
    for index, item in enumerate(tables, start=1):
        links.append(
            AtomicLink(
                link_id=f"table-{index}",
                claim=item.operation,
                table_id=item.table_id,
                source_ranges=item.source_ranges,
                kind="fact",
                priority=100 + index,
            )
        )
    conclusion = None
    inference_ids = tuple(
        item.link_id for item in links if item.kind == "inference_link"
    )
    if len(inference_ids) >= 2:
        conclusion = ComposedConclusion(
            text="Composed multi-hop inference from the cited atomic links.",
            kind="inference",
            link_ids=inference_ids,
        )
    prose_parts = [
        item.citation_text.strip()
        for item in fusion.evidence
        if item.citation_text.strip()
    ]
    for item in tables:
        prose_parts.append(f"{item.operation} {item.source_ranges} {item.rows}")
    status: str = "complete" if prose_parts else "partial"
    return AnswerPayload(
        answer_text=" ".join(prose_parts)[:8000] or "Insufficient authorized evidence.",
        citations=citations,
        atomic_links=tuple(links),
        composed_conclusion=conclusion,
        table_citations=table_citations,
        status="complete" if status == "complete" else "partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
