"""Answer-origin sanitization and invented-ID filtering."""

from __future__ import annotations

import re
from typing import Literal

from smart_rag_core.query_answer.assembly import allowed_chunk_ids, allowed_table_ids
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    ScopeDegradationReason,
)
from smart_rag_core.query_routing.models import TableEvidenceRecord

GENERAL_DOCUMENT_REFUSAL = (
    "I can answer general questions from model knowledge, but I cannot claim "
    "to have searched company documents on this path. Ask a document-scoped "
    "question for a cited answer."
)
DEGRADED_NO_COMPANY_SEARCH = (
    "Company documents were not searched because the question's scope could "
    "not be established."
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


def empty_no_retrieval(
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


def apply_degraded_scope_framing(
    payload: AnswerPayload,
    *,
    scope_degradation_reason: ScopeDegradationReason | None,
) -> AnswerPayload:
    """Prefix explicit no-company-search wording on degraded general answers.

    Args:
        payload: Sanitized general-chat payload.
        scope_degradation_reason: Server-derived failed-profile reason.

    Returns:
        The same payload, or a copy whose prose states that company
        documents were not searched.
    """

    if scope_degradation_reason is None:
        return payload
    text = payload.answer_text.strip()
    if DEGRADED_NO_COMPANY_SEARCH.casefold() in text.casefold():
        return payload
    framed = f"{DEGRADED_NO_COMPANY_SEARCH} {text}".strip()
    return payload.model_copy(update={"answer_text": framed})


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
        return empty_no_retrieval(
            GENERAL_DOCUMENT_REFUSAL,
            status="refused",
            origin=origin,
        )
    return AnswerPayload(
        answer_text=payload.answer_text,
        status=payload.status,
        answer_origin=origin,
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
        if citation_has_allowed_source(item, chunks, table_ids)
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


def citation_has_allowed_source(
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
