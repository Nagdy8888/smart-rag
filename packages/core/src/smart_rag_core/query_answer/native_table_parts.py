"""Copy consecutive canonical table fragments with separate source ownership."""

from __future__ import annotations

import re
from collections.abc import Sequence

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import with_derived_answer_text
from smart_rag_core.query_answer.table_copy import copy_pipe_table
from smart_rag_core.query_fusion.models import ScoredPassage


def copy_native_table_parts(
    payload: AnswerPayload, sources: Sequence[ScoredPassage]
) -> AnswerPayload | None:
    """Combine only matching-header fragments from the same version on adjacent pages."""
    if not sources:
        return None
    first = sources[0]
    match = re.search(r"(?m)^\s*\|[^\n]+\|\s*$", first.citation_text)
    if match is None:
        return None
    header = match.group().strip()
    paragraphs: list[AnswerParagraph] = []
    links: list[AtomicLink] = []
    citations: list[AnswerCitation] = []
    seen: set[str] = set()
    complete = True
    for source in sources:
        candidate = re.search(r"(?m)^\s*\|[^\n]+\|\s*$", source.citation_text)
        if (
            source.document_id != first.document_id
            or source.version_id != first.version_id
            or source.page_number is None
            or first.page_number is None
            or not 0 <= source.page_number - first.page_number <= 1
            or candidate is None
            or candidate.group().strip() != header
            or source.citation_text in seen
        ):
            continue
        part = copy_pipe_table(payload, source, caption="")
        if part is None:
            continue
        if (
            len(paragraphs) + len(part.paragraphs) > 6
            or len(citations) + len(part.citations) > 12
            or sum(len(p.text) + 2 for p in [*paragraphs, *part.paragraphs]) > 8000
        ):
            complete = False
            break
        offset = len(paragraphs)
        remap = {
            link.link_id: f"table-part-{offset}-{link.link_id}"
            for link in part.atomic_links
        }
        paragraphs.extend(
            p.model_copy(
                update={
                    "paragraph_index": p.paragraph_index + offset,
                    "link_ids": tuple(remap[link_id] for link_id in p.link_ids),
                }
            )
            for p in part.paragraphs
        )
        links.extend(
            link.model_copy(update={"link_id": remap[link.link_id]})
            for link in part.atomic_links
        )
        citations.extend(
            c.model_copy(
                update={
                    "paragraph_index": (c.paragraph_index or 0) + offset,
                    "atomic_link_id": remap.get(
                        c.atomic_link_id or "", c.atomic_link_id
                    ),
                }
            )
            for c in part.citations
        )
        seen.add(source.citation_text)
        complete = complete and part.status == "complete"
    if not paragraphs:
        return None
    return with_derived_answer_text(
        payload.model_copy(
            update={
                "paragraphs": tuple(paragraphs),
                "atomic_links": tuple(links),
                "citations": tuple(citations),
                "status": "complete" if complete else "partial",
            }
        )
    )
