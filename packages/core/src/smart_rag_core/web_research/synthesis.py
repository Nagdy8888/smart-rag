"""Prompt isolation and mock synthesis for persisted Web sources."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.query_answer.models import AnswerPayload, AtomicLink
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.web_research.bounds import WEB_MAX_CITATIONS, WEB_MAX_EXCERPT_CHARS
from smart_rag_core.web_research.models import WebCitation, WebSourceRecord

_SOURCE_OPEN = "<<untrusted-web-source id={source_id}>>"
_SOURCE_CLOSE = "<<end-untrusted-web-source id={source_id}>>"


def isolate_web_sources(sources: tuple[WebSourceRecord, ...]) -> str:
    """Render persisted excerpts with unique source-id delimiters.

    Retrieved text is prompt-injection. The model may cite only the
    delimited ``web_source_id`` values.

    Args:
        sources: Persisted sources for this run.

    Returns:
        Delimited untrusted block. Never includes company passages.
    """

    parts: list[str] = []
    for source in sources:
        open_tag = _SOURCE_OPEN.format(source_id=source.web_source_id)
        close_tag = _SOURCE_CLOSE.format(source_id=source.web_source_id)
        excerpt = source.excerpt[:WEB_MAX_EXCERPT_CHARS]
        parts.append(
            f"{open_tag}\ntitle={source.title}\nurl_omitted\n{excerpt}\n{close_tag}"
        )
    return "\n".join(parts)


def citations_from_persisted_ids(
    *,
    sources: tuple[WebSourceRecord, ...],
    claimed_ids: tuple[str, ...],
    spans: tuple[str, ...],
) -> tuple[WebCitation, ...]:
    """Keep citations whose source id was persisted and span is contained.

    Args:
        sources: Persisted sources.
        claimed_ids: Model-claimed ``web_source_id`` values.
        spans: Parallel spans. Missing spans use a prefix of the excerpt.

    Returns:
        At most twelve verified Web citations. Invented ids are dropped.
    """

    by_id = {item.web_source_id: item for item in sources}
    kept: list[WebCitation] = []
    for index, source_id in enumerate(claimed_ids):
        if len(kept) >= WEB_MAX_CITATIONS:
            break
        record = by_id.get(source_id)
        if record is None:
            continue
        span = spans[index] if index < len(spans) else record.excerpt[:180]
        if not span or span not in record.excerpt:
            continue
        kept.append(WebCitation(web_source_id=source_id, span=span))
    return tuple(kept)


def mock_web_answer(
    *,
    query: str,
    sources: tuple[WebSourceRecord, ...],
) -> AnswerPayload:
    """Build a grounded Web draft from persisted excerpts without a model.

    Args:
        query: Sanitized user query. Unused in the prose except as a cue.
        sources: Persisted sources. Must be non-empty.

    Returns:
        Answer with ``answer_origin=web``, empty company citations, and
        spans copied from excerpts.
    """

    del query
    citations: list[WebCitation] = []
    links: list[AtomicLink] = []
    sentences: list[str] = []
    for source in sources[:WEB_MAX_CITATIONS]:
        span = source.excerpt[:180].strip()
        if not span:
            continue
        citations.append(WebCitation(web_source_id=source.web_source_id, span=span))
        link_id = f"web-{uuid4().hex[:8]}"
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=span[:200],
                web_source_ids=(source.web_source_id,),
            )
        )
        sentences.append(span)
    text = " ".join(sentences)[:4000] or "Insufficient public web evidence."
    status = "complete" if citations else "refused"
    return AnswerPayload(
        answer_text=text,
        citations=(),
        web_citations=tuple(citations),
        atomic_links=tuple(links),
        table_citations=(),
        status=status,
        answer_origin=KnowledgeScope.WEB,
    )
