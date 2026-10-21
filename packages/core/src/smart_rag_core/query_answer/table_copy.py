"""Copy a named canonical pipe table without clipping rows to one citation."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_fusion.models import ScoredPassage

_FOOTER = re.compile(r"^(?:\d+\s*\|\s*Chapter\s+\d+|[A-Z][A-Za-z -]+\s*\|\s*\d+)")


def copy_pipe_table(
    payload: AnswerPayload, source: ScoredPassage, *, caption: str
) -> AnswerPayload | None:
    """Pack complete table rows into bounded claims with exact source slices.

    Repeated page headers and running footers are layout. Each displayed part
    repeats the original column header; cell values and row order are unchanged.

    Args:
        payload: Prior answer, used only for origin/compatible metadata.
        source: One authorized canonical passage containing the table.
        caption: Exact requested caption, or empty for a native row chunk.

    Returns:
        Source-grounded table payload, or ``None`` when no complete table exists.
    """
    text = source.citation_text
    title = re.search(rf"(?im)^\s*{re.escape(caption)}\.", text) if caption else None
    start = title.start() if title is not None else 0
    lines: list[tuple[int, str]] = []
    offset = start
    for raw in text[start:].splitlines(keepends=True):
        lines.append((offset, raw.rstrip("\r\n")))
        offset += len(raw)
    header_index = next(
        (
            i
            for i in range(len(lines) - 1)
            if lines[i][1].strip().startswith("|")
            and "-" in lines[i + 1][1]
            and re.fullmatch(r"[\s|:\-]+", lines[i + 1][1])
        ),
        None,
    )
    if header_index is None:
        return None
    header = lines[header_index][1].strip()
    separator = lines[header_index + 1][1].strip()
    rows: list[tuple[int, str]] = []
    for position, line in lines[header_index + 2 :]:
        stripped = line.strip()
        if not stripped or _FOOTER.match(stripped):
            continue
        if stripped == header or re.fullmatch(r"[\s|:\-]+", stripped):
            continue
        if not stripped.startswith("|") or stripped.count("|") != header.count("|"):
            break
        rows.append((position, line))
    if not rows:
        return None
    groups: list[list[tuple[int, str]]] = []
    group: list[tuple[int, str]] = []
    size = len(header) + len(separator) + 2
    complete = True
    for row in rows:
        if size + len(row[1]) + 1 > 1900 and group:
            groups.append(group)
            group = []
            size = len(header) + len(separator) + 2
        if len(groups) >= 6 or size + len(row[1]) + 1 > 1900:
            complete = False
            break
        group.append(row)
        size += len(row[1]) + 1
    if group:
        groups.append(group)
    if not groups:
        return None
    paragraphs: list[AnswerParagraph] = []
    links: list[AtomicLink] = []
    citations: list[AnswerCitation] = []
    for index, part in enumerate(groups):
        link_id = "table-block-1" if index == 0 else f"table-block-{index + 1}"
        display = "\n".join((header, separator, *(line.strip() for _, line in part)))
        span_start = part[0][0]
        if index == 0 and title is not None:
            display = caption + "\n" + display
            span_start = title.start()
        span = text[span_start : part[-1][0] + len(part[-1][1])]
        if len(span) > 2000 or len(citations) + (len(span) + 999) // 1000 > 12:
            complete = False
            break
        paragraphs.append(
            AnswerParagraph(paragraph_index=index, text=display, link_ids=(link_id,))
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=display,
                chunk_ids=(source.chunk_id,),
                kind="fact",
                priority=10 + index,
            )
        )
        citations.extend(
            AnswerCitation(
                chunk_id=source.chunk_id,
                span=span[at : at + 1000],
                atomic_link_id=link_id,
                paragraph_index=index,
            )
            for at in range(0, len(span), 1000)
        )
    if not paragraphs:
        return None
    return payload.model_copy(
        update={
            "answer_text": "\n\n".join(p.text for p in paragraphs),
            "paragraphs": tuple(paragraphs),
            "citations": tuple(citations),
            "table_citations": (),
            "atomic_links": tuple(links),
            "composed_conclusion": None,
            "refused_links": (),
            "status": "complete" if complete else "partial",
        }
    )
