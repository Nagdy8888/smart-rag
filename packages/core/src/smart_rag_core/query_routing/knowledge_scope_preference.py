"""Apply a client search-scope preference onto an automatic scope decision."""

from __future__ import annotations

import re

from smart_rag_core.query_profile.extract import extract_deterministic
from smart_rag_core.query_routing.knowledge_scope import (
    KnowledgeScope,
    KnowledgeScopeDecision,
    company_intent_signal,
    has_company_phrase,
)
from smart_rag_core.query_routing.knowledge_scope_web import has_web_privacy_risk
from smart_rag_core.query_routing.signals import (
    is_greeting,
    is_product_help,
    is_small_talk,
    is_user_text_transform,
)
from smart_rag_core.search_scope import RequestedSearchScope


def _public_comparison(query: str) -> bool:
    """Recognize a standalone public-source comparison, not a private follow-up.

    Comparison/table shape alone is not a disclosure risk. Explicit company
    references, identifiers, document scope, secrets and referential follow-ups
    retain the existing clarification guard.
    """
    extract = extract_deterministic(query)
    return (
        query.lstrip().lower().startswith("compare ")
        and re.search(r"(?i)\b(?:cite|official|public|documentation|standard)\b", query)
        is not None
        and re.search(
            r"(?i)\b(?:our|internal|uploaded|attached|previous|earlier|those|these|them)\b",
            query,
        )
        is None
        and not extract.codes
        and extract.document_scope == "none"
        and not has_company_phrase(query)
        and not has_web_privacy_risk(query)
    )


def _social_opener(query: str) -> bool:
    """Return whether the whole message is a greeting or small talk.

    Args:
        query: Original user text.

    Returns:
        True for a whole-message greeting or bounded small-talk phrase.
    """

    return is_greeting(query) or is_small_talk(query)


def apply_requested_search_scope(
    query: str,
    automatic: KnowledgeScopeDecision,
    requested: RequestedSearchScope,
) -> KnowledgeScopeDecision:
    """Apply a client source preference to an automatic scope decision.

    Greetings, small talk, product help, and user-text transforms keep their
    current handling. Other substantive prompts honor explicit Company,
    General, or Web. Auto returns the automatic decision unchanged.
    Requested Company never manufactures ``company_signal=True``. Explicit
    Web with company signals, source IDs, or secret-like tokens clarifies
    instead of calling a provider.

    Args:
        query: Original user text. Untrusted.
        automatic: Decision from ``classify_knowledge_scope``.
        requested: Client source preference fixed at admission.

    Returns:
        Effective scope decision used by preparation and the route matrix.
    """

    if requested is RequestedSearchScope.AUTO:
        return automatic
    extract = extract_deterministic(query)
    query_company = company_intent_signal(query, extract)
    if is_product_help(query) and not query_company:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
            confidence=1.0,
            company_signal=False,
            general_signal=True,
        )
    if _social_opener(query) and not query_company:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
            confidence=1.0,
            company_signal=False,
            general_signal=True,
        )
    if is_user_text_transform(query):
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.USER_SUPPLIED_TEXT,
            confidence=1.0,
            company_signal=automatic.company_signal,
            general_signal=automatic.general_signal,
        )
    if requested is RequestedSearchScope.COMPANY_DOCUMENTS:
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.COMPANY_DOCUMENTS,
            confidence=1.0,
            company_signal=automatic.company_signal,
            general_signal=automatic.general_signal,
        )
    if requested is RequestedSearchScope.WEB:
        if _public_comparison(query):
            return KnowledgeScopeDecision(
                knowledge_scope=KnowledgeScope.WEB,
                confidence=1.0,
                company_signal=False,
                general_signal=False,
            )
        if (
            query_company
            or automatic.company_signal
            or has_web_privacy_risk(query)
            or has_company_phrase(query)
        ):
            return KnowledgeScopeDecision(
                knowledge_scope=KnowledgeScope.AMBIGUOUS,
                confidence=1.0,
                company_signal=True,
                general_signal=False,
            )
        return KnowledgeScopeDecision(
            knowledge_scope=KnowledgeScope.WEB,
            confidence=1.0,
            company_signal=automatic.company_signal,
            general_signal=automatic.general_signal,
        )
    return KnowledgeScopeDecision(
        knowledge_scope=KnowledgeScope.GENERAL_KNOWLEDGE,
        confidence=1.0,
        company_signal=automatic.company_signal,
        general_signal=automatic.general_signal,
    )
