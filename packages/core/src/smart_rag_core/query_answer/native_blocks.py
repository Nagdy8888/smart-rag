"""Attach cited code, tables, and figures when the prose does not already show them.

A figure is also inserted when the question asks for one, or when the
answer already uses that figure's caption. A placed native block keeps a
citation to its fusion chunk so persistence can store a chip.
"""

from __future__ import annotations

import re

from smart_rag_core.query_answer.figure_placement import (
    figure_caption_text,
    place_owned_figures,
)
from smart_rag_core.query_answer.format_shape import answer_has_markdown_pipe_table
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
)
from smart_rag_core.query_answer.native_selection import (
    relevant_native_fusion,
    requested_artifact_labels,
)
from smart_rag_core.query_answer.versions import MAX_ANSWER_CITATIONS
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage

_FENCE_BODY = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_FIGURE = re.compile(r"\[\[figure:([0-9a-fA-F-]{1,64})\]\]")
_MAX_PARAGRAPHS = 6
_MAX_NATIVE_CHARS = 4000
_NATIVE_SPAN_CHARS = 500


def figure_ids_in_text(text: str) -> tuple[str, ...]:
    """Return figure ids marked in answer text.

    Args:
        text: Released answer text.

    Returns:
        Ids in order, without duplicates.
    """

    found: list[str] = []
    for match in _FIGURE.finditer(text):
        figure_id = match.group(1)
        if figure_id not in found:
            found.append(figure_id)
    return tuple(found)


def strip_figure_marks(text: str) -> str:
    """Remove figure marks from prose. The UI renders the image separately.

    Args:
        text: Paragraph text that may contain ``[[figure:...]]``.

    Returns:
        Text without those marks.
    """

    return _FIGURE.sub("", text).strip()


def _listing_in_fence(existing: str, body: str) -> bool:
    """Return whether a fence already holds the full cited listing.

    Args:
        existing: Released answer text.
        body: Cited code with its original line breaks.

    Returns:
        True only when some fence contains the whole listing.
    """

    return any(body in match.group(1) for match in _FENCE_BODY.finditer(existing))


def _native_block(
    item_kind: str, body: str, figure_id: str | None, existing: str
) -> str:
    """Return the display block for one cited native passage.

    Args:
        item_kind: ``code``, ``table``, or ``figure``.
        body: Stripped citation text. Must already be non-empty.
        figure_id: Figure id when ``item_kind`` is ``figure``.
        existing: Answer text already released, including blocks chosen
            earlier in this call.

    Returns:
        A fence, pipe table, or figure mark, or an empty string when that
        full body is already present or the block cannot fit one paragraph.
    """

    if item_kind == "code":
        if _listing_in_fence(existing, body):
            return ""
        text = f"```\n{body}\n```"
    elif item_kind == "table":
        if body in existing:
            return ""
        text = body
    else:
        body = figure_caption_text(body)
        mark = f"[[figure:{figure_id}]]" if figure_id else ""
        if figure_id and figure_id in existing:
            return ""
        text = f"{body}\n{mark}".strip()
    if not text or len(text) > _MAX_NATIVE_CHARS or len(body) > _MAX_NATIVE_CHARS:
        return ""
    return text


_FIGURE_ASK = re.compile(r"\bfigures?\b", re.IGNORECASE)
_FIGURE_LABEL = re.compile(r"\d+\s*-\s*\d+")
_CONTENT_WORD = re.compile(r"[A-Za-z][A-Za-z'-]{5,}")
_OVERLAP_SKIP = frozenset(
    {
        "about",
        "after",
        "again",
        "agent",
        "agents",
        "because",
        "before",
        "between",
        "figure",
        "figures",
        "should",
        "system",
        "systems",
        "their",
        "there",
        "these",
        "those",
        "through",
        "where",
        "which",
        "while",
        "would",
    }
)


def _content_words(text: str) -> set[str]:
    """Return distinctive words used to see whether a figure was used.

    Args:
        text: Query, answer, or figure caption.

    Returns:
        Lowercased words of at least six letters, without generic terms.
    """

    return {
        word.casefold()
        for word in _CONTENT_WORD.findall(text)
        if word.casefold() not in _OVERLAP_SKIP
    }


def _figure_is_useful(
    query: str, answer: str, citation_text: str, *, alone: bool
) -> bool:
    """Return whether this figure belongs in the visible answer.

    Args:
        query: User question.
        answer: Visible answer text.
        citation_text: Figure caption or description from evidence.
        alone: True when this is the only figure in the evidence.

    Returns:
        True when the question asks for a figure and this one matches,
        or when the answer already uses the figure's distinctive words.
    """

    labels = {re.sub(r"\s+", "", label) for label in _FIGURE_LABEL.findall(query)}
    caption = citation_text.casefold()
    folded_caption = caption.replace(" ", "")
    label_hit = any(label.replace(" ", "") in folded_caption for label in labels)
    overlap = _content_words(answer) & _content_words(citation_text)
    asks = _FIGURE_ASK.search(query) is not None
    if asks and (label_hit or alone or len(overlap) >= 2):
        return True
    return len(overlap) >= 2


def insert_useful_figures(
    payload: AnswerPayload, fusion: FusionResult, query: str
) -> AnswerPayload:
    """Append a figure mark when the question or the answer uses that figure.

    A mark already present is left in place. The caption is the evidence
    text, bounded to one paragraph. No model call.

    Args:
        payload: Released company answer.
        fusion: Canonical evidence for this run.
        query: Original user text. Untrusted.

    Returns:
        The same payload when no figure is missing, otherwise a copy
        with at most six paragraphs.
    """

    if not fusion.evidence or not payload.paragraphs:
        return payload
    link_ids = payload.paragraphs[0].link_ids
    if not link_ids:
        return payload
    figures = [
        item
        for item in fusion.evidence
        if item.content_kind == "figure"
        and item.figure_id
        and item.citation_text.strip()
    ]
    if not figures:
        return payload
    existing = payload.answer_text
    blocks: list[str] = []
    alone = len(figures) == 1
    for item in figures:
        figure_id = item.figure_id or ""
        if figure_id in existing:
            continue
        if not _figure_is_useful(query, existing, item.citation_text, alone=alone):
            continue
        caption = " ".join(figure_caption_text(item.citation_text).split())[
            :240
        ].strip()
        text = (
            f"{caption}\n[[figure:{figure_id}]]"
            if caption
            else f"[[figure:{figure_id}]]"
        )
        if len(text) > _MAX_NATIVE_CHARS:
            text = f"[[figure:{figure_id}]]"
        blocks.append(text)
        existing = f"{existing}\n{text}"
    if not blocks:
        return payload
    kept = list(payload.paragraphs)
    selected: list[str] = []
    length = len(payload.answer_text)
    for block in blocks:
        if len(kept) + len(selected) >= _MAX_PARAGRAPHS:
            continue
        if length + len(block) + 2 > 16_384:
            continue
        selected.append(block)
        length += len(block) + 2
    omitted = len(selected) < len(blocks)
    blocks = selected
    if not blocks:
        return payload.model_copy(update={"status": "partial"}) if omitted else payload
    paragraphs = [
        paragraph.model_copy(update={"paragraph_index": index})
        for index, paragraph in enumerate(kept)
    ]
    start = len(paragraphs)
    paragraphs.extend(
        AnswerParagraph(paragraph_index=start + offset, text=text, link_ids=link_ids)
        for offset, text in enumerate(blocks)
    )
    answer_text = "\n\n".join(item.text for item in paragraphs)
    return payload.model_copy(
        update={
            "paragraphs": tuple(paragraphs),
            "answer_text": answer_text,
            "status": "partial" if omitted else payload.status,
        }
    )


def attach_native_evidence(
    payload: AnswerPayload, fusion: FusionResult, *, user_query: str | None = None
) -> AnswerPayload:
    """Append cited code, pipe tables, and figure marks missing from the prose.

    Native blocks use only free slots; checked paragraphs are never evicted. A full
    listing, pipe table, or figure id that is already present is not
    repeated. A body longer than one paragraph is omitted rather than cut.
    When bounds omit a new block, the answer is explicitly partial.
    Each placed block gains one citation when that chunk is not already
    cited. The span is a prefix of the chunk text, at most 500 characters.

    Args:
        payload: Released company answer.
        fusion: Canonical evidence for this run.
        user_query: Original question for requested/cited artifact selection.

    Returns:
        The same payload when nothing native is missing and every placed
        block is already cited. Otherwise a copy with at most six
        paragraphs and at most twelve citations.
    """

    if not fusion.evidence or not payload.paragraphs:
        return payload
    if user_query is not None:
        if requested_artifact_labels(user_query, "table") and any(
            link.link_id.startswith("table-block-") for link in payload.atomic_links
        ):
            return payload
        fusion = relevant_native_fusion(payload, fusion, user_query)
        # Referencing a source does not ask to append all code/table bodies.
        # Images remain automatic whenever the answer uses their evidence.
        want_code = bool(
            re.search(
                r"(?i)\b(?:show|reproduce|copy|fenced|snippet|code|python)\b",
                user_query,
            )
        )
        want_table = bool(
            re.search(
                r"(?i)\b(?:table|compare|comparison|markdown)\b|\u062c\u062f\u0648\u0644",
                user_query,
            )
        )
        fusion = fusion.model_copy(
            update={
                "evidence": tuple(
                    item
                    for item in fusion.evidence
                    if item.content_kind not in {"code", "table"}
                    or (item.content_kind == "code" and want_code)
                    or (item.content_kind == "table" and want_table)
                )
            }
        )
        if any(
            link.link_id.startswith(("cited-table-", "table-block-"))
            for link in payload.atomic_links
        ):
            fusion = fusion.model_copy(
                update={
                    "evidence": tuple(
                        item for item in fusion.evidence if item.content_kind != "table"
                    )
                }
            )
    payload = place_owned_figures(payload, fusion)
    placed = _append_missing_native_blocks(payload, fusion)
    return _cite_placed_native_blocks(placed, fusion)


def _append_missing_native_blocks(
    payload: AnswerPayload, fusion: FusionResult
) -> AnswerPayload:
    """Append native blocks that the released prose does not already show.

    Args:
        payload: Released company answer with at least one paragraph.
        fusion: Canonical evidence for this run.

    Returns:
        The same payload when every native body is already present or no
        link can own a new paragraph. Otherwise a copy with at most six
        paragraphs.
    """

    link_ids = payload.paragraphs[0].link_ids
    if not link_ids:
        return payload
    existing = payload.answer_text
    blocks: list[str] = []
    for item in fusion.evidence:
        if item.content_kind not in {"code", "table", "figure"}:
            continue
        if item.content_kind == "table":
            owners = {
                citation.paragraph_index
                for citation in payload.citations
                if citation.chunk_id == item.chunk_id
            }
            if any(
                paragraph.paragraph_index in owners
                and answer_has_markdown_pipe_table(paragraph.text)
                for paragraph in payload.paragraphs
            ):
                continue
        body = item.citation_text.strip()
        if not body:
            continue
        text = _native_block(item.content_kind, body, item.figure_id, existing)
        if not text:
            continue
        blocks.append(text)
        existing = f"{existing}\n{text}"
    if not blocks:
        return payload
    kept = list(payload.paragraphs)
    selected: list[str] = []
    length = len(payload.answer_text)
    for block in blocks:
        if len(kept) + len(selected) >= _MAX_PARAGRAPHS:
            continue
        if length + len(block) + 2 > 16_384:
            continue
        selected.append(block)
        length += len(block) + 2
    omitted = len(selected) < len(blocks)
    blocks = selected
    if not blocks:
        return payload.model_copy(update={"status": "partial"}) if omitted else payload
    paragraphs = [
        paragraph.model_copy(update={"paragraph_index": index})
        for index, paragraph in enumerate(kept)
    ]
    start = len(paragraphs)
    paragraphs.extend(
        AnswerParagraph(paragraph_index=start + offset, text=text, link_ids=link_ids)
        for offset, text in enumerate(blocks)
    )
    kept_count = len(kept)
    citations = tuple(
        item
        for item in payload.citations
        if item.paragraph_index is None or item.paragraph_index < kept_count
    )
    table_citations = tuple(
        item
        for item in payload.table_citations
        if item.paragraph_index is None or item.paragraph_index < kept_count
    )
    answer_text = "\n\n".join(item.text for item in paragraphs)
    return payload.model_copy(
        update={
            "paragraphs": tuple(paragraphs),
            "citations": citations,
            "table_citations": table_citations,
            "answer_text": answer_text,
            "status": "partial" if omitted else payload.status,
        }
    )


def _cite_placed_native_blocks(
    payload: AnswerPayload, fusion: FusionResult
) -> AnswerPayload:
    """Add one citation for each placed native chunk that is not cited yet.

    Args:
        payload: Answer after missing blocks have been appended.
        fusion: Canonical evidence for this run.

    Returns:
        The same payload when every placed native chunk is already cited.
        Otherwise a copy whose citation list stays within the answer cap.
    """

    citations = list(payload.citations)
    cited = {item.chunk_id for item in citations if item.chunk_id}
    added = False
    for item in fusion.evidence:
        if len(citations) >= MAX_ANSWER_CITATIONS:
            break
        if item.chunk_id in cited or not _native_body_placed(item, payload.answer_text):
            continue
        span = _contained_prefix(item.citation_text)
        if not span:
            continue
        paragraph_index = _owning_paragraph(payload.paragraphs, item)
        link_id = _paragraph_link(payload.paragraphs, paragraph_index)
        citations.append(
            AnswerCitation(
                chunk_id=item.chunk_id,
                span=span,
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
        cited.add(item.chunk_id)
        added = True
    if not added:
        return payload
    return payload.model_copy(update={"citations": tuple(citations)})


def _native_body_placed(item: ScoredPassage, answer: str) -> bool:
    """Return whether this fusion block is already visible in the answer.

    Args:
        item: One fused passage.
        answer: Released answer text, including blocks appended in this call.

    Returns:
        True for a fenced listing, a pipe table, or a figure id that the
        answer already shows.
    """

    if item.content_kind not in {"code", "table", "figure"}:
        return False
    body = item.citation_text.strip()
    if not body:
        return False
    if item.content_kind == "code":
        return _listing_in_fence(answer, body) or body in answer
    if item.content_kind == "table":
        return body in answer
    return bool(item.figure_id and item.figure_id in answer)


def _contained_prefix(citation_text: str) -> str:
    """Return a citation span that is a prefix of the chunk text.

    Args:
        citation_text: Canonical passage text.

    Returns:
        A non-empty substring of ``citation_text``, at most 500 characters,
        or empty when the passage has no usable text.
    """

    stripped = citation_text.strip()
    if not stripped:
        return ""
    prefix = stripped[:_NATIVE_SPAN_CHARS]
    if prefix in citation_text:
        return prefix
    return citation_text[:_NATIVE_SPAN_CHARS]


def _owning_paragraph(
    paragraphs: tuple[AnswerParagraph, ...], item: ScoredPassage
) -> int | None:
    """Return the paragraph index that shows this native block.

    Args:
        paragraphs: Released paragraphs.
        item: Fusion passage whose body or figure id is in the answer.

    Returns:
        A paragraph index from 0 through 5, or ``None`` when no paragraph
        holds the block.
    """

    needle = (
        item.figure_id if item.content_kind == "figure" else item.citation_text.strip()
    )
    if not needle:
        return None
    for paragraph in paragraphs:
        if needle in paragraph.text and paragraph.paragraph_index <= 5:
            return paragraph.paragraph_index
    return None


def _paragraph_link(
    paragraphs: tuple[AnswerParagraph, ...], paragraph_index: int | None
) -> str | None:
    """Return the first link id on the paragraph that owns a native block.

    Args:
        paragraphs: Released paragraphs.
        paragraph_index: Index returned by ``_owning_paragraph``.

    Returns:
        A link id, or ``None`` when that paragraph has no links.
    """

    if paragraph_index is None:
        return None
    for paragraph in paragraphs:
        if paragraph.paragraph_index == paragraph_index and paragraph.link_ids:
            return paragraph.link_ids[0]
    return None
