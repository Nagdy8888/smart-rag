"""Validate located quotes and use them in the company answer call."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.verifier import VERBATIM_MIN_CHARS
from smart_rag_core.query_answer.versions import (
    LOCATE_MAX_QUOTES,
    LOCATE_QUOTE_MAX_CHARS,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

LOCATED_QUOTES_HEADER = "Located quotes:"
MODEL_QUERY_MAX_CHARS = 2000


@dataclass(frozen=True, slots=True)
class LocatedQuote:
    """One quote copied exactly from a canonical passage.

    Attributes:
        chunk_id: Canonical chunk UUID that contains ``text``.
        text: Exact substring of that chunk's citation text.
    """

    chunk_id: str
    text: str


def exact_source_quote(claim: str, source: str) -> str | None:
    """Return the exact source substring that matches a claim word for word.

    Whitespace between words may differ (line breaks, indentation); every
    other character must match exactly.

    Args:
        claim: Claim text returned by the locate call.
        source: Canonical passage text.

    Returns:
        The matching substring of ``source``, or None.
    """

    tokens = claim.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, source)
    return match.group(0) if match else None


def located_quotes(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    limit: int = LOCATE_MAX_QUOTES,
) -> tuple[LocatedQuote, ...]:
    """Keep locate claims that occur word for word in a cited passage.

    Args:
        payload: Parsed locate payload after invented-id filtering.
        fusion: Evidence sent to the locate call.
        limit: Maximum quotes to keep.

    Returns:
        Validated quotes in provider order, deduplicated.
    """

    texts = {item.chunk_id: item.citation_text for item in fusion.evidence}
    found: list[LocatedQuote] = []
    seen: set[tuple[str, str]] = set()
    for link in payload.atomic_links:
        if len(found) >= limit:
            break
        if link.kind != "fact" or link.table_id:
            continue
        for chunk_id in link.chunk_ids:
            quote = exact_source_quote(link.claim, texts.get(chunk_id, ""))
            if quote is None:
                continue
            if not VERBATIM_MIN_CHARS <= len(quote) <= LOCATE_QUOTE_MAX_CHARS:
                continue
            if (chunk_id, quote) in seen:
                continue
            seen.add((chunk_id, quote))
            found.append(LocatedQuote(chunk_id=chunk_id, text=quote))
            break
    return tuple(found)


def located_query(
    query: str,
    quotes: Sequence[LocatedQuote],
    *,
    max_chars: int = MODEL_QUERY_MAX_CHARS,
) -> str:
    """Append validated quotes to the model-facing query.

    The original query is never changed for shape detection or release;
    only the text sent to the answer model gets the list.

    Args:
        query: Original user query.
        quotes: Validated quotes.
        max_chars: Upper bound for the returned text.

    Returns:
        ``query`` alone when no quote fits, otherwise ``query`` followed by
        a ``Located quotes:`` list.
    """

    lines = [query, "", LOCATED_QUOTES_HEADER]
    added = 0
    for quote in quotes:
        line = "- " + " ".join(quote.text.split())
        if len("\n".join([*lines, line])) > max_chars:
            break
        lines.append(line)
        added += 1
    return "\n".join(lines) if added else query


def quote_fallback_payload(
    answer: AnswerPayload,
    quotes: Sequence[LocatedQuote],
) -> AnswerPayload | None:
    """Release validated quotes when the answer call returned nothing usable.

    Args:
        answer: Answer payload after parsing, binding, and structural repairs.
        quotes: Validated quotes from the locate call.

    Returns:
        A ``partial`` payload with one cited paragraph per quote when the
        answer is refused or has no links and quotes exist; otherwise None.
    """

    if not quotes or (answer.status != "refused" and answer.atomic_links):
        return None
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    links: list[AtomicLink] = []
    for index, quote in enumerate(quotes):
        link_id = f"locate-{index + 1}"
        paragraphs.append(
            AnswerParagraph(paragraph_index=index, text=quote.text, link_ids=(link_id,))
        )
        citations.append(
            AnswerCitation(
                chunk_id=quote.chunk_id,
                span=quote.text,
                paragraph_index=index,
                atomic_link_id=link_id,
            )
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=quote.text,
                chunk_ids=(quote.chunk_id,),
                kind="fact",
                priority=index + 1,
            )
        )
    return AnswerPayload(
        paragraphs=tuple(paragraphs),
        citations=tuple(citations),
        atomic_links=tuple(links),
        status="partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
