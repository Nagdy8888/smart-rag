"""Attach cited code, tables, and figures when the prose does not already show them."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AnswerParagraph, AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult

_FENCE = re.compile(r"```")
_FIGURE = re.compile(r"\[\[figure:([0-9a-fA-F-]{1,64})\]\]")


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


def attach_native_evidence(
    payload: AnswerPayload, fusion: FusionResult
) -> AnswerPayload:
    """Append cited code, pipe tables, and figure marks missing from the prose.

    Args:
        payload: Released company answer.
        fusion: Canonical evidence for this run.

    Returns:
        The same payload when nothing native is missing, otherwise a copy
        with extra paragraphs. At most six paragraphs are kept.
    """

    if not fusion.evidence or len(payload.paragraphs) >= 6:
        return payload
    existing = payload.answer_text
    extras: list[AnswerParagraph] = []
    next_index = len(payload.paragraphs)
    for item in fusion.evidence:
        if next_index > 5 or item.content_kind not in {"code", "table", "figure"}:
            continue
        body = item.citation_text.strip()
        if not body:
            continue
        if item.content_kind == "code":
            if body in existing or _FENCE.search(existing):
                continue
            text = f"```\n{body}\n```"
        elif item.content_kind == "table":
            if body in existing or body.splitlines()[0] in existing:
                continue
            text = body
        else:
            mark = f"[[figure:{item.figure_id}]]" if item.figure_id else ""
            if item.figure_id and item.figure_id in existing:
                continue
            text = f"{body}\n{mark}".strip()
        if not text or len(text) > 4000:
            continue
        link_ids = payload.paragraphs[0].link_ids if payload.paragraphs else ()
        if not link_ids:
            continue
        extras.append(
            AnswerParagraph(
                paragraph_index=next_index, text=text[:4000], link_ids=link_ids
            )
        )
        next_index += 1
        existing = f"{existing}\n{text}"
    if not extras:
        return payload
    paragraphs = (*payload.paragraphs, *extras)
    answer_text = "\n\n".join(item.text for item in paragraphs)
    return payload.model_copy(
        update={"paragraphs": paragraphs, "answer_text": answer_text[:16384]}
    )
