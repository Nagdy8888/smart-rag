"""Cited-page opening windows used by extractive answer salvage.

Page windows are exact substrings of fitted evidence. They occupy
paragraph and verifier slots ahead of later claims so a source-word
or code-reproduce ask still releases the named page.
"""

from __future__ import annotations

from smart_rag_core.query_answer.models import (
    AnswerParagraph,
    AnswerPayload,
)
from smart_rag_core.query_answer.paragraphs import with_derived_answer_text
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_PARAGRAPHS,
    MAX_CITATION_SPAN_CHARS,
    MAX_VERIFIER_LINKS,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.retrieval.rerank import (
    named_page_numbers,
    wants_cited_page_windows,
)


def _opening_exact_span(text: str) -> str:
    """Copy the opening of a passage as an exact evidence substring.

    The window is capped at ``MAX_CITATION_SPAN_CHARS`` and ends on a
    sentence boundary when one falls inside the cap. The result stays a
    substring of ``text`` so citation alignment still succeeds.

    Args:
        text: Passage citation text.

    Returns:
        Exact opening substring, or empty when ``text`` is blank.
    """

    if not text or not text.strip():
        return ""
    start = len(text) - len(text.lstrip())
    end_limit = min(len(text), start + MAX_CITATION_SPAN_CHARS)
    window_end = end_limit
    if end_limit < len(text):
        last_sentence = -1
        for index, char in enumerate(text[start:end_limit]):
            if char in ".!?":
                last_sentence = index
        if last_sentence >= 0:
            window_end = start + last_sentence + 1
    span = text[start:window_end].strip()
    if not span or span not in text:
        return ""
    return span[:MAX_CITATION_SPAN_CHARS]


def _continuation_exact_span(text: str) -> str:
    """Copy the passage text that starts where the opening ends.

    The window begins at the first non-space character after the opening
    and is capped at ``MAX_CITATION_SPAN_CHARS``, ending on a sentence
    boundary when one falls inside the cap. The result stays a substring
    of ``text``.

    Args:
        text: Passage citation text.

    Returns:
        Exact continuation substring, or empty when the passage does not
        continue past the opening.
    """

    opening = _opening_exact_span(text)
    if not opening:
        return ""
    start = text.find(opening)
    if start < 0:
        return ""
    rest_start = start + len(opening)
    while rest_start < len(text) and text[rest_start].isspace():
        rest_start += 1
    if rest_start >= len(text):
        return ""
    end_limit = min(len(text), rest_start + MAX_CITATION_SPAN_CHARS)
    window_end = end_limit
    if end_limit < len(text):
        last_sentence = -1
        for index, char in enumerate(text[rest_start:end_limit]):
            if char in ".!?":
                last_sentence = index
        if last_sentence >= 0:
            window_end = rest_start + last_sentence + 1
    span = text[rest_start:window_end].strip()
    if not span or span not in text or span == opening:
        return ""
    return span[:MAX_CITATION_SPAN_CHARS]


def _page_windows(text: str) -> tuple[str, ...]:
    """Return the opening and, when the passage continues, the next window.

    Args:
        text: Passage citation text.

    Returns:
        One or two exact substrings. A continuation that repeats the
        opening is omitted.
    """

    opening = _opening_exact_span(text)
    later = _continuation_exact_span(text)
    windows: list[str] = []
    if opening:
        windows.append(opening)
    if later and later != opening:
        windows.append(later)
    return tuple(windows)


def fill_cited_page_opening(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload | None:
    """Append page windows for a source-word or code-reproduce ask.

    Each fitted passage on the named page contributes its opening and,
    when the passage continues, the text that starts where that opening
    ends. Page windows take the paragraph and verifier slots first. Six
    windows are kept in page, hybrid-rank, then chunk-id order. A window
    already present in the answer is not copied again. An existing code
    block stays when a slot remains.

    Args:
        payload: Company answer after code/table salvages.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Updated payload, the original when every window is already
        released, or None when this ask is not a cited-page source-word
        or code-reproduce ask, or no cited-page passage has text.
    """

    pages = set(named_page_numbers(user_query))
    if not pages or not wants_cited_page_windows(user_query):
        return None
    matched = [
        item
        for item in fusion.evidence
        if item.page_number is not None and int(item.page_number) in pages
    ]
    matched.sort(
        key=lambda item: (
            int(item.page_number or 0),
            item.hybrid_rank if item.hybrid_rank is not None else 10_000,
            item.chunk_id,
        )
    )
    chosen: list[tuple[str, str]] = []
    for item in matched:
        for span in _page_windows(item.citation_text or ""):
            chosen.append((item.chunk_id, span))
            if len(chosen) >= MAX_ANSWER_PARAGRAPHS:
                break
        if len(chosen) >= MAX_ANSWER_PARAGRAPHS:
            break
    if not chosen:
        return None
    missing = [
        (chunk_id, span)
        for chunk_id, span in chosen
        if not _opening_already_released(payload, span)
    ]
    if not missing:
        return payload
    return _append_page_openings(payload, missing)


def _opening_already_released(payload: AnswerPayload, span: str) -> bool:
    """Return whether a paragraph already contains the collapsed opening.

    Args:
        payload: Current company answer.
        span: Exact opening substring.

    Returns:
        True when the collapsed opening is already paragraph text.
    """

    compact = " ".join(span.split()).casefold()
    if not compact:
        return True
    return any(
        compact in " ".join(paragraph.text.split()).casefold()
        for paragraph in payload.paragraphs
    )


def _append_page_openings(
    payload: AnswerPayload,
    openings: list[tuple[str, str]],
) -> AnswerPayload:
    """Append cited-page openings, dropping later claims that do not fit.

    Args:
        payload: Prior company answer.
        openings: ``(chunk_id, exact span)`` pairs not already released.
            At most ``MAX_ANSWER_PARAGRAPHS`` items.

    Returns:
        Payload whose page openings occupy slots ahead of later claims.
        Paragraph indexes stay contiguous.
    """

    if not openings:
        return payload
    slot_cap = min(MAX_ANSWER_PARAGRAPHS, MAX_VERIFIER_LINKS)
    room = max(0, slot_cap - len(openings))
    kept: list[AnswerParagraph] = []
    kept_link_count = 0
    for paragraph in sorted(payload.paragraphs, key=lambda item: item.paragraph_index):
        if len(kept) >= room:
            break
        added_links = len(paragraph.link_ids)
        if kept_link_count + added_links + len(openings) > slot_cap:
            break
        kept.append(paragraph)
        kept_link_count += added_links
    kept_indexes = {item.paragraph_index for item in kept}
    kept_link_ids = {link_id for item in kept for link_id in item.link_ids}
    index_of = {
        paragraph.paragraph_index: new_index for new_index, paragraph in enumerate(kept)
    }
    paragraphs = [
        paragraph.model_copy(
            update={"paragraph_index": index_of[paragraph.paragraph_index]}
        )
        for paragraph in kept
    ]
    citations = [
        citation.model_copy(
            update={"paragraph_index": index_of[citation.paragraph_index]}
        )
        for citation in payload.citations
        if citation.paragraph_index in index_of
        and (
            citation.atomic_link_id is None or citation.atomic_link_id in kept_link_ids
        )
    ]
    table_citations = [
        citation.model_copy(
            update={"paragraph_index": index_of[citation.paragraph_index]}
        )
        for citation in payload.table_citations
        if citation.paragraph_index in kept_indexes
        and citation.paragraph_index in index_of
    ]
    links = [link for link in payload.atomic_links if link.link_id in kept_link_ids]
    used_ids = {link.link_id for link in links}
    next_number = 1
    # Deferred: generate_anchor_salvage imports this module at load time.
    from smart_rag_core.query_answer.generate_anchor_salvage import (
        append_anchor_claim,
    )

    for chunk_id, span in openings:
        while f"page-opening-{next_number}" in used_ids:
            next_number += 1
        link_id = f"page-opening-{next_number}"
        used_ids.add(link_id)
        next_number += 1
        drafted = append_anchor_claim(
            payload.model_copy(
                update={
                    "paragraphs": tuple(paragraphs),
                    "citations": tuple(citations),
                    "table_citations": tuple(table_citations),
                    "atomic_links": tuple(links),
                    "status": payload.status,
                }
            ),
            chunk_id=chunk_id,
            span=span,
            link_id=link_id,
            collapse_whitespace=True,
            priority=0,
        )
        paragraphs = list(drafted.paragraphs)
        citations = list(drafted.citations)
        links = list(drafted.atomic_links)
        table_citations = list(drafted.table_citations)
    updated = payload.model_copy(
        update={
            "paragraphs": tuple(paragraphs),
            "citations": tuple(citations),
            "table_citations": tuple(table_citations),
            "atomic_links": tuple(links),
            "status": "complete",
            "refused_links": tuple(
                item
                for item in payload.refused_links
                if item not in {link.link_id for link in links}
            ),
        }
    )
    return with_derived_answer_text(updated)
