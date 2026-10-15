"""Attach cited code, tables, and figures when the prose does not already show them."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AnswerParagraph, AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult

_FENCE_BODY = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_FIGURE = re.compile(r"\[\[figure:([0-9a-fA-F-]{1,64})\]\]")
_MAX_PARAGRAPHS = 6
_MAX_NATIVE_CHARS = 4000


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


def _native_block(item_kind: str, body: str, figure_id: str | None, existing: str) -> str:
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
        mark = f"[[figure:{figure_id}]]" if figure_id else ""
        if figure_id and figure_id in existing:
            return ""
        text = f"{body}\n{mark}".strip()
    if not text or len(text) > _MAX_NATIVE_CHARS or len(body) > _MAX_NATIVE_CHARS:
        return ""
    return text


def attach_native_evidence(
    payload: AnswerPayload, fusion: FusionResult
) -> AnswerPayload:
    """Append cited code, pipe tables, and figure marks missing from the prose.

    Native blocks take paragraph slots ahead of trailing prose. A full
    listing, pipe table, or figure id that is already present is not
    repeated. A body longer than one paragraph is omitted rather than cut.

    Args:
        payload: Released company answer.
        fusion: Canonical evidence for this run.

    Returns:
        The same payload when nothing native is missing, otherwise a copy
        with at most six paragraphs.
    """

    if not fusion.evidence or not payload.paragraphs:
        return payload
    link_ids = payload.paragraphs[0].link_ids
    if not link_ids:
        return payload
    existing = payload.answer_text
    blocks: list[str] = []
    for item in fusion.evidence:
        if item.content_kind not in {"code", "table", "figure"}:
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
    while len(kept) + len(blocks) > _MAX_PARAGRAPHS and kept:
        kept.pop()
    blocks = blocks[: _MAX_PARAGRAPHS - len(kept)]
    if not blocks:
        return payload
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
            "answer_text": answer_text[:16384],
        }
    )
