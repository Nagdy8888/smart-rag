"""Split from ``generate_grounded.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.generate_code_salvage import (
    extractive_block_already_released,
    replace_with_extractive_block,
)
from smart_rag_core.query_answer.generate_literals import (
    distinctive_query_literals,
    distinctive_query_names,
    is_empty_refusal,
    passage_query_overlap,
    significant_query_terms,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import (
    with_derived_answer_text,
)
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_PARAGRAPHS,
    MAX_CITATION_SPAN_CHARS,
    MAX_VERIFIER_LINKS,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.retrieval.rerank import (
    named_page_numbers,
    wants_cited_page_windows,
)

_TABLE_BLOCK_LINK_ID = "table-block-1"

_ANCHOR_CLAIM_LINK_ID = "anchor-claim-1"

_ANCHOR_CLAIM_LINK_IDS = frozenset({_ANCHOR_CLAIM_LINK_ID, "page-claim-1"})


def salvage_anchor_claim_fill(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Inject omitted fitted evidence spans (anchor-gated).

    When the ask names a page and wants source words or reproduced code,
    appends the opening of every fitted passage on that page and the
    continuation that starts where that opening ends. An existing code
    block or anchor claim does not block those windows. A table block
    still returns before the fill so the table body keeps its slots.
    Otherwise appends at most one contiguous span that clears the anchor
    gate: two distinct anchor hits in the chosen passage, or one
    distinctive literal/name of length ≥4.

    Args:
        payload: Company answer after code/table salvages.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload with added page openings or one anchor claim, or unchanged.
    """

    if any(link.link_id == _TABLE_BLOCK_LINK_ID for link in payload.atomic_links):
        return payload
    opened = _fill_cited_page_opening(payload, fusion, user_query=user_query)
    if opened is not None:
        return opened
    if any(link.link_id in _ANCHOR_CLAIM_LINK_IDS for link in payload.atomic_links):
        return payload
    anchors = _page_claim_anchors(user_query)
    if not anchors:
        return payload
    strong_keys = _strong_anchor_keys(user_query)
    for item in _ranked_fill_passages(fusion, user_query=user_query):
        text = item.citation_text or ""
        if not _passage_satisfies_anchor_gate(text, anchors, strong_keys=strong_keys):
            continue
        span = _contiguous_anchor_span(text, anchors)
        if not span:
            continue
        if extractive_block_already_released(payload, span):
            continue
        if is_empty_refusal(payload):
            return replace_with_extractive_block(
                payload,
                chunk_id=item.chunk_id,
                span=span,
                link_id=_ANCHOR_CLAIM_LINK_ID,
            )
        return _append_anchor_claim(
            payload,
            chunk_id=item.chunk_id,
            span=span,
            link_id=_ANCHOR_CLAIM_LINK_ID,
        )
    return payload


def _contiguous_anchor_span(text: str, anchors: tuple[str, ...]) -> str:
    """Copy one contiguous evidence span that covers matching anchors.

    Args:
        text: Passage citation text.
        anchors: Query-derived anchors that must appear in ``text``.

    Returns:
        Exact evidence substring capped at ``MAX_CITATION_SPAN_CHARS``, or
        empty when fewer than one anchor hits.
    """

    if not text or not anchors:
        return ""
    lowered = text.casefold()
    hit_ranges: list[tuple[int, int]] = []
    for anchor in anchors:
        needle = anchor.casefold()
        if not needle:
            continue
        start = lowered.find(needle)
        if start < 0:
            continue
        hit_ranges.append((start, start + len(anchor)))
    if not hit_ranges:
        return ""
    start = min(item[0] for item in hit_ranges)
    end = max(item[1] for item in hit_ranges)
    # Expand to nearby line/sentence boundaries for a readable claim.
    while start > 0 and text[start - 1] not in ".\n!?":
        start -= 1
        if end - start >= MAX_CITATION_SPAN_CHARS:
            break
    while end < len(text) and text[end - 1 : end] not in ".\n!?":
        end += 1
        if end - start >= MAX_CITATION_SPAN_CHARS:
            break
    span = text[start:end].strip()
    if not span:
        return ""
    return span[:MAX_CITATION_SPAN_CHARS]


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


def _fill_cited_page_opening(
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
    for chunk_id, span in openings:
        while f"page-opening-{next_number}" in used_ids:
            next_number += 1
        link_id = f"page-opening-{next_number}"
        used_ids.add(link_id)
        next_number += 1
        drafted = _append_anchor_claim(
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


def _strong_anchor_keys(user_query: str) -> frozenset[str]:
    """Return casefolded distinctive literal/name keys (length ≥4).

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Strong anchor keys used for the single-anchor hit gate.
    """

    cited_pages = {str(page) for page in named_page_numbers(user_query)}
    keys: set[str] = set()
    for token in (
        *distinctive_query_literals(user_query),
        *distinctive_query_names(user_query),
    ):
        if len(token) < 4:
            continue
        if token in cited_pages or token.casefold() in cited_pages:
            continue
        keys.add(token.casefold())
    return frozenset(keys)


def _passage_satisfies_anchor_gate(
    text: str,
    anchors: tuple[str, ...],
    *,
    strong_keys: frozenset[str],
) -> bool:
    """Return whether a passage is strong enough to fill from.

    Requires at least two distinct anchor hits, or one distinctive
    literal/name of length ≥4.

    Args:
        text: Passage citation text.
        anchors: Query-derived anchors.
        strong_keys: Casefolded distinctive literal/name keys.

    Returns:
        True when the passage clears the hit gate.
    """

    hits = _anchor_hits_in_text(text, anchors)
    if len(hits) >= 2:
        return True
    if len(hits) == 1 and hits[0].casefold() in strong_keys:
        return True
    return False


def _page_claim_anchors(user_query: str) -> tuple[str, ...]:
    """Return query-derived anchors for anchor-gated claim fill.

    Drops bare page numbers the query already cited so anchors point at
    topical literals rather than the page cite itself.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Deduplicated anchors in encounter order.
    """

    cited_pages = {str(page) for page in named_page_numbers(user_query)}
    found: list[str] = []
    seen: set[str] = set()
    for token in (
        *distinctive_query_literals(user_query),
        *distinctive_query_names(user_query),
        *significant_query_terms(user_query),
    ):
        key = token.casefold()
        if key in seen or token in cited_pages or key in cited_pages:
            continue
        if key in {"page", "pages", "section", "wording", "words", "quote"}:
            continue
        if len(token) < 3:
            continue
        seen.add(key)
        found.append(token)
    return tuple(found)


def _anchor_hits_in_text(text: str, anchors: tuple[str, ...]) -> tuple[str, ...]:
    """Return anchors that appear in ``text`` (case-insensitive).

    Args:
        text: Passage citation text.
        anchors: Query-derived anchors.

    Returns:
        Matching anchors in input order.
    """

    if not text or not anchors:
        return ()
    lowered = text.casefold()
    return tuple(anchor for anchor in anchors if anchor.casefold() in lowered)


def salvage_named_page_claim_fill(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str,
) -> AnswerPayload:
    """Cycle 4 wrapper: delegate to anchor-gated claim fill.

    Args:
        payload: Company answer after code/table salvages.
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Payload after ``salvage_anchor_claim_fill``.
    """

    return salvage_anchor_claim_fill(payload, fusion, user_query=user_query)


def _allows_fill_link_id(link_id: str) -> bool:
    """Return whether salvage may assign ``link_id``.

    Args:
        link_id: Proposed atomic link id.

    Returns:
        True for the anchor claim ids and ``page-opening-N``.
    """

    if link_id in _ANCHOR_CLAIM_LINK_IDS:
        return True
    head, sep, tail = link_id.rpartition("-")
    return bool(sep) and head == "page-opening" and tail.isdigit() and int(tail) >= 1


def _append_anchor_claim(
    payload: AnswerPayload,
    *,
    chunk_id: str,
    span: str,
    link_id: str = _ANCHOR_CLAIM_LINK_ID,
    collapse_whitespace: bool = False,
    priority: int = 10,
) -> AnswerPayload:
    """Append one extractive claim without wiping prior company claims.

    Args:
        payload: Prior company answer.
        chunk_id: Fusion chunk that holds ``span``.
        span: Exact citation span from evidence.
        link_id: Anchor or page-opening claim id to assign.
        collapse_whitespace: When True, the visible claim joins wrapped
            lines into spaces. The citation span stays exact.
        priority: Verifier rank. Lower is kept ahead of ordinary facts.

    Returns:
        Payload with one added anchor claim, or unchanged when empty.
    """

    exact = span.strip()[:MAX_CITATION_SPAN_CHARS]
    if not exact:
        return payload
    if collapse_whitespace:
        display = " ".join(exact.split())
    else:
        display = re.sub(
            r"\n{2,}",
            "\n",
            exact.replace("\r\n", "\n").replace("\r", "\n"),
        ).strip()
    if not display:
        return payload
    if any(link.link_id == link_id for link in payload.atomic_links):
        return payload
    if not _allows_fill_link_id(link_id):
        return payload
    next_index = (
        max((item.paragraph_index for item in payload.paragraphs), default=-1) + 1
    )
    if next_index > 5:
        return payload
    paragraph = AnswerParagraph(
        paragraph_index=next_index,
        text=display[:4000],
        link_ids=(link_id,),
    )
    citation = AnswerCitation(
        chunk_id=chunk_id,
        span=exact,
        atomic_link_id=link_id,
        paragraph_index=next_index,
    )
    link = AtomicLink(
        link_id=link_id,
        claim=display[:2000],
        chunk_ids=(chunk_id,),
        kind="fact",
        priority=priority,
    )
    updated = payload.model_copy(
        update={
            "paragraphs": (*payload.paragraphs, paragraph),
            "citations": (*payload.citations, citation),
            "atomic_links": (*payload.atomic_links, link),
            "status": "complete",
            "refused_links": tuple(
                item for item in payload.refused_links if item != link_id
            ),
        }
    )
    return with_derived_answer_text(updated)


def _ranked_fill_passages(
    fusion: FusionResult,
    *,
    user_query: str,
) -> list[ScoredPassage]:
    """Rank fitted passages for anchor claim fill.

    Args:
        fusion: Fitted canonical evidence.
        user_query: Original user text. Untrusted.

    Returns:
        Page-matching passages first, then overlap-ranked remainder.
    """

    pages = set(named_page_numbers(user_query))
    page_first = [
        item
        for item in fusion.evidence
        if pages and item.page_number is not None and int(item.page_number) in pages
    ]
    page_ids = {item.chunk_id for item in page_first}
    rest = [item for item in fusion.evidence if item.chunk_id not in page_ids]

    def _rank(items: list[ScoredPassage]) -> list[ScoredPassage]:
        """Sort passages by query overlap, then hybrid rank, then id."""

        return sorted(
            items,
            key=lambda item: (
                -passage_query_overlap(user_query, item.citation_text),
                item.hybrid_rank or 10_000,
                item.chunk_id,
            ),
        )

    return [*_rank(page_first), *_rank(rest)]
