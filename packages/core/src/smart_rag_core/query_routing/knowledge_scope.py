"""Typed knowledge-scope classification for the general-chat strict split.

The preparation model may classify remaining natural-language scope only. It
never selects Hybrid/Combined/Table or authorizes evidence. Company signals
always override a model result of general knowledge.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_profile.extract import (
    DeterministicExtract,
    extract_deterministic,
)
from smart_rag_core.query_routing.signals import (
    is_corpus_wide_theme,
    is_current_relationship,
    is_graph_inspection,
    is_greeting,
    is_historical_relationship,
    is_low_confidence_relationship,
    is_product_help,
    is_user_text_transform,
    is_whole_document_summary,
)

SCOPE_CONFIDENCE_THRESHOLD = 0.80
"""Minimum accepted model confidence for a non-ambiguous scope."""

_COMPANY_PHRASES = (
    "my company",
    "our documents",
    "company knowledge",
    "our document",
)
_COMPANY_WORDS = re.compile(
    r"\b(our|workspace|uploaded)\b",
    flags=re.IGNORECASE,
)
_SOURCE_ID = re.compile(
    r"\b(p4-src-\d{4}|INV-SR-\d{4}|SKU-P4-[A-Z0-9]{3}|PRJ-[A-Z0-9]{3,12})\b",
    flags=re.IGNORECASE,
)
_GENERAL_FIXTURES = (
    re.compile(r"\bcapital of france\b", flags=re.IGNORECASE),
    re.compile(r"\bexplain photosynthesis\b", flags=re.IGNORECASE),
)
_COMPANY_FIXTURES = (
    re.compile(r"\bstatus of INV-SR-1001\b", flags=re.IGNORECASE),
    re.compile(r"\bour refund period\b", flags=re.IGNORECASE),
)
_MEMORY_COMPANY_HINT = re.compile(
    r"\b(chunk[_-]?id|source[_-]?id|INV-SR-\d{4}|p4-src-\d{4}|citation)\b",
    flags=re.IGNORECASE,
)


class MemoryLike(Protocol):
    """Minimal memory record used for company follow-up detection."""

    role: str
    content: str


class KnowledgeScope(StrEnum):
    """Origin of the answer the route is allowed to produce."""

    GENERAL_KNOWLEDGE = "general_knowledge"
    COMPANY_DOCUMENTS = "company_documents"
    USER_SUPPLIED_TEXT = "user_supplied_text"
    DETERMINISTIC = "deterministic"
    AMBIGUOUS = "ambiguous"


class NoRetrievalAnswerMode(StrEnum):
    """How a NoRetrieval plan must answer without company retrieval."""

    DETERMINISTIC_CHAT = "deterministic_chat"
    GENERAL_MODEL = "general_model"
    USER_TEXT_MODEL = "user_text_model"
    CLARIFICATION = "clarification"


class KnowledgeScopeDecision(BaseModel):
    """Structured scope result used by preparation and the route matrix.

    Attributes:
        knowledge_scope: Selected scope. Company signals always win.
        confidence: Closed unit interval. Model values below 0.80 become
            ``AMBIGUOUS``.
        company_signal: Deterministic company/document evidence.
        general_signal: Deterministic general-knowledge evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    knowledge_scope: KnowledgeScope
    confidence: float = Field(ge=0.0, le=1.0)
    company_signal: bool
    general_signal: bool


def has_company_followup_memory(memory: Sequence[MemoryLike]) -> bool:
    """Return whether recent memory shows a prior company-document answer.

    Args:
        memory: Bounded untrusted conversation records.

    Returns:
        True when an assistant turn contains citation or source-id evidence.
    """

    for record in memory:
        if record.role != "assistant":
            continue
        if _MEMORY_COMPANY_HINT.search(record.content):
            return True
    return False


def has_company_phrase(query: str) -> bool:
    """Return whether the query uses an unambiguous company phrase or word.

    The isolated word ``policy`` is intentionally ignored so general questions
    such as “Explain monetary policy” remain possible.

    Args:
        query: Original user text.

    Returns:
        True when a listed company phrase, word, or source id is present.
    """

    lowered = query.lower()
    if any(phrase in lowered for phrase in _COMPANY_PHRASES):
        return True
    if _COMPANY_WORDS.search(query) is not None:
        return True
    return _SOURCE_ID.search(query) is not None


def has_general_fixture(query: str) -> bool:
    """Return whether the query matches a deterministic general fixture.

    Args:
        query: Original user text.

    Returns:
        True for the mock-mode general-knowledge examples.
    """

    return any(pattern.search(query) for pattern in _GENERAL_FIXTURES)


def has_company_fixture(query: str) -> bool:
    """Return whether the query matches a deterministic company fixture.

    Args:
        query: Original user text.

    Returns:
        True for the mock-mode company-document examples.
    """

    return any(pattern.search(query) for pattern in _COMPANY_FIXTURES)


def company_intent_signal(query: str, extract: DeterministicExtract) -> bool:
    """Return whether typed extract or query text is a company-document signal.

    Args:
        query: Original user text.
        extract: Deterministic Phase 4 extract.

    Returns:
        True when identifiers, document scope, or company intents are present.
    """

    if extract.codes or extract.document_scope != "none":
        return True
    if extract.table_intent or extract.query_type is QueryType.STRUCTURED_TABULAR:
        return True
    if extract.relationship_intent or extract.query_type is QueryType.RELATIONSHIP_MULTI_HOP:
        return True
    if is_current_relationship(query, extract) or is_historical_relationship(
        query, extract
    ):
        return True
    if is_low_confidence_relationship(query, extract):
        return True
    if is_graph_inspection(query) or is_corpus_wide_theme(query):
        return True
    if extract.media_dependence:
        return True
    if extract.negation_scope != "none":
        return True
    if extract.query_type is QueryType.BROAD_SUMMARY or is_whole_document_summary(
        query, extract
    ):
        return True
    if extract.query_type is QueryType.MULTI_PART or query.lower().startswith("compare "):
        return True
    if extract.query_type is QueryType.EXACT_IDENTIFIER:
        return True
    if has_company_phrase(query) or has_company_fixture(query):
        return True
    return False


def general_intent_signal(query: str) -> bool:
    """Return whether the query has a deterministic general-knowledge signal.

    Args:
        query: Original user text.

    Returns:
        True for greetings, product-help, or the mock general fixtures.
    """

    return is_greeting(query) or is_product_help(query) or has_general_fixture(query)


def parse_model_knowledge_scope(raw: str | None) -> KnowledgeScope | None:
    """Parse a model-emitted scope string.

    Args:
        raw: Optional enum value from the structured preparation payload.

    Returns:
        A known ``KnowledgeScope``, or ``None`` when missing or invalid.
    """

    if raw is None or not raw.strip():
        return None
    try:
        return KnowledgeScope(raw.strip())
    except ValueError:
        return None


def scope_requires_model(
    query: str,
    *,
    memory: Sequence[MemoryLike] = (),
) -> bool:
    """Return whether remaining natural-language scope needs the prep call.

    Args:
        query: Original user text.
        memory: Bounded untrusted conversation records.

    Returns:
        True when deterministic rules and fixtures do not settle scope.
    """

    extract = extract_deterministic(query)
    query_company = company_intent_signal(query, extract)
    memory_company = has_company_followup_memory(memory)
    general = general_intent_signal(query)
    if query_company and general:
        return False
    if is_greeting(query):
        return False
    if is_product_help(query) and not query_company:
        return False
    if query_company or (memory_company and not general):
        return False
    if is_user_text_transform(query):
        return False
    if has_general_fixture(query):
        return False
    return True


def classify_knowledge_scope(
    query: str,
    *,
    memory: Sequence[MemoryLike] = (),
    model_scope: str | None = None,
    model_confidence: float | None = None,
    model_available: bool = False,
) -> KnowledgeScopeDecision:
    """Classify knowledge scope with the approved strict-split priority.

    Args:
        query: Original user text. Untrusted.
        memory: Bounded recent messages. Never source documents.
        model_scope: Optional scope from the single preparation payload.
        model_confidence: Optional confidence from that same payload.
        model_available: True when the one preparation call returned a payload.

    Returns:
        Frozen scope decision. Company signals override model output.
        Standalone greetings are ``general_knowledge``.
    """

    extract = extract_deterministic(query)
    query_company = company_intent_signal(query, extract)
    memory_company = has_company_followup_memory(memory)
    company = query_company or memory_company
    general = general_intent_signal(query)
    user_text = is_user_text_transform(query)

    if is_greeting(query):
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
            confidence=1.0,
            company_signal=query_company,
            general_signal=True,
        )
    if is_product_help(query) and not query_company:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
            confidence=1.0,
            company_signal=False,
            general_signal=True,
        )
    if company and general:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.AMBIGUOUS,
            confidence=1.0,
            company_signal=True,
            general_signal=True,
        )
    if company:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.COMPANY_DOCUMENTS,
            confidence=1.0,
            company_signal=True,
            general_signal=general,
        )
    if user_text:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.USER_SUPPLIED_TEXT,
            confidence=1.0,
            company_signal=False,
            general_signal=general,
        )
    if is_product_help(query) or has_general_fixture(query):
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
            confidence=1.0,
            company_signal=False,
            general_signal=True,
        )
    if not model_available:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.AMBIGUOUS,
            confidence=0.0,
            company_signal=False,
            general_signal=False,
        )
    parsed = parse_model_knowledge_scope(model_scope)
    confidence = 0.0 if model_confidence is None else model_confidence
    if parsed is None or confidence < SCOPE_CONFIDENCE_THRESHOLD:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.AMBIGUOUS,
            confidence=confidence,
            company_signal=False,
            general_signal=False,
        )
    if parsed is KnowledgeScope.GENERAL_KNOWLEDGE and company:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.COMPANY_DOCUMENTS,
            confidence=1.0,
            company_signal=True,
            general_signal=True,
        )
    return KnowledgeScopeDecision(
        knowledge_scope=parsed,
        confidence=confidence,
        company_signal=company,
        general_signal=parsed is KnowledgeScope.GENERAL_KNOWLEDGE,
    )


def no_retrieval_mode_for_scope(scope: KnowledgeScope) -> NoRetrievalAnswerMode | None:
    """Return the NoRetrieval answer mode for a classified scope.

    Args:
        scope: Classified knowledge scope.

    Returns:
        A NoRetrieval mode, or ``None`` when company documents require
        citations and the existing retrieval matrix.
    """

    mapping = {
        KnowledgeScope.DETERMINISTIC: NoRetrievalAnswerMode.DETERMINISTIC_CHAT,
        KnowledgeScope.GENERAL_KNOWLEDGE: NoRetrievalAnswerMode.GENERAL_MODEL,
        KnowledgeScope.USER_SUPPLIED_TEXT: NoRetrievalAnswerMode.USER_TEXT_MODEL,
        KnowledgeScope.AMBIGUOUS: NoRetrievalAnswerMode.CLARIFICATION,
        KnowledgeScope.COMPANY_DOCUMENTS: None,
    }
    return mapping[scope]
