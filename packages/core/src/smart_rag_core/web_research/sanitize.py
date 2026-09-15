"""Strip secrets and refuse company passages before any Exa call."""

from __future__ import annotations

import re

from smart_rag_core.gateways.exa_search import EXA_MAX_QUERY_CHARS
from smart_rag_core.web_research.exceptions import WebResearchError

_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b",
)
_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
)
_SIGNED = re.compile(
    r"(?i)("
    r"\bsk-[A-Za-z0-9]{16,}\b|"
    r"\bBearer\s+[A-Za-z0-9._\-]+|"
    r"X-Amz-Signature=|"
    r"/storage/v1/object/sign/|"
    r"[?&](token|sig|signature)=[A-Za-z0-9%\-_]{16,}"
    r")"
)
_COMPANY_MARKERS = (
    "<<untrusted-source>>",
    "<<untrusted-data-",
    "canonical passage",
    "chunk_id=",
    "document_id=",
    "signed_url",
)


def assert_no_company_passage(text: str, *, forbidden_snippets: tuple[str, ...] = ()) -> None:
    """Refuse a query that already contains company or memory passages.

    Args:
        text: Candidate Exa query.
        forbidden_snippets: Extra strings that must never be forwarded,
            such as conversation memory or fusion citation text.

    Raises:
        WebResearchError: ``company_passage_forbidden``.
    """

    lowered = text.lower()
    for marker in _COMPANY_MARKERS:
        if marker in lowered:
            raise WebResearchError("company_passage_forbidden")
    for snippet in forbidden_snippets:
        stripped = snippet.strip()
        if len(stripped) >= 24 and stripped in text:
            raise WebResearchError("company_passage_forbidden")


def sanitize_exa_query(
    text: str,
    *,
    forbidden_snippets: tuple[str, ...] = (),
) -> str:
    """Return rewritten user text safe to send to Exa.

    Strips emails, UUIDs, JWTs, and signed-URL patterns. Does not send
    conversation memory. Empty results fail closed.

    Args:
        text: Rewritten user query. Untrusted.
        forbidden_snippets: Company/memory strings that must not appear.

    Returns:
        Query truncated to the Exa character cap.

    Raises:
        WebResearchError: Company passage, privacy residue, or empty query.
    """

    assert_no_company_passage(text, forbidden_snippets=forbidden_snippets)
    cleaned = _EMAIL.sub(" ", text)
    cleaned = _UUID.sub(" ", cleaned)
    cleaned = _JWT.sub(" ", cleaned)
    cleaned = _SIGNED.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        raise WebResearchError("web_search_invalid_response")
    return cleaned[:EXA_MAX_QUERY_CHARS]
