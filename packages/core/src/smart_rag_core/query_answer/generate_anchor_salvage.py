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
from smart_rag_core.query_answer.generate_page_openings import (
    fill_cited_page_opening,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.native_selection import requested_artifact_labels
from smart_rag_core.query_answer.paragraphs import (
    with_derived_answer_text,
)
from smart_rag_core.query_answer.versions import (
    MAX_CITATION_SPAN_CHARS,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.retrieval.rerank import named_page_numbers

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
    appends one quote of every fitted passage on that page, up to 4,000
    characters, until the paragraph slots are full. An existing code
    block or anchor claim does not block those quotes. A table block
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
    if requested_artifact_labels(user_query, "figure") and not named_page_numbers(
        user_query
    ):
        return payload
    opened = fill_cited_page_opening(payload, fusion, user_query=user_query)
    if opened is not None:
        return opened
    if any(link.link_id == "code-def-1" for link in payload.atomic_links):
        return payload
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
        return append_anchor_claim(
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
    return (
        bool(sep)
        and head in {"page-opening", "query-facet"}
        and tail.isdigit()
        and int(tail) >= 1
    )


def append_anchor_claim(
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
        collapse_whitespace: When True, the visible paragraph joins
            wrapped lines into spaces and may run to 4,000 characters.
            The citation span stays an exact substring of at most 1,000
            characters.
        priority: Verifier rank. Lower is kept ahead of ordinary facts.

    Returns:
        Payload with one added anchor claim, or unchanged when empty.
    """

    raw = span.strip()
    exact = raw[:MAX_CITATION_SPAN_CHARS]
    if not exact:
        return payload
    if collapse_whitespace:
        display = " ".join(raw[:4000].split())
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
