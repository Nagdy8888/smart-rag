"""Place a cited figure beside its existing claim without consuming a prose slot."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_CITATIONS,
    MAX_CITATION_SPAN_CHARS,
)
from smart_rag_core.query_fusion.models import FusionResult


def figure_caption_text(raw: str) -> str:
    """Keep the exact caption suffix while excluding preceding PDF code/footer text."""
    match = re.search(r"(?im)^\s*Figure\s+\d+[-\u2013]\d+[.:]", raw)
    return raw[match.start() :].strip() if match is not None else raw.strip()


def place_owned_figures(payload: AnswerPayload, fusion: FusionResult) -> AnswerPayload:
    """Append an exact source description and figure to their existing owner.

    The caller filters exact requested artifacts first. Both the paragraph's link
    and its citation must own the figure chunk; a topical match is insufficient.
    Original prose, indices, links, and citation spans survive. The full bounded
    description gets an exact citation when no owned span already contains it.
    Existing character/citation ceilings still apply, and replay is idempotent.
    """
    paragraphs = list(payload.paragraphs)
    links = {link.link_id: link for link in payload.atomic_links}
    citations = list(payload.citations)
    existing = payload.answer_text
    changed = False
    for item in fusion.evidence:
        if item.content_kind != "figure" or not item.figure_id:
            continue
        marker = f"[[figure:{item.figure_id}]]"
        if marker in existing:
            continue
        caption = figure_caption_text(item.citation_text)
        if not caption or len(caption) > MAX_CITATION_SPAN_CHARS:
            continue
        for index, paragraph in enumerate(paragraphs):
            owners = {
                link_id
                for link_id in paragraph.link_ids
                if link_id in links and item.chunk_id in links[link_id].chunk_ids
            }
            if not owners or not any(
                citation.chunk_id == item.chunk_id
                and citation.paragraph_index == paragraph.paragraph_index
                and citation.atomic_link_id in owners
                for citation in payload.citations
            ):
                continue
            owned = [
                c
                for c in citations
                if c.chunk_id == item.chunk_id
                and c.paragraph_index == paragraph.paragraph_index
                and c.atomic_link_id in owners
            ]
            needs_citation = not any(c.span and caption in c.span for c in owned)
            if needs_citation and len(citations) >= MAX_ANSWER_CITATIONS:
                continue
            block = marker if caption in paragraph.text else f"{caption}\n{marker}"
            text = f"{paragraph.text}\n{block}"
            if len(text) > 4000 or len(existing) + len(block) + 1 > 16_384:
                continue
            if needs_citation:
                citations.append(
                    AnswerCitation(
                        chunk_id=item.chunk_id,
                        span=caption,
                        paragraph_index=paragraph.paragraph_index,
                        atomic_link_id=owned[0].atomic_link_id,
                    )
                )
            paragraphs[index] = paragraph.model_copy(update={"text": text})
            existing = "\n\n".join(p.text for p in paragraphs)
            changed = True
            break
    return (
        payload.model_copy(
            update={
                "paragraphs": tuple(paragraphs),
                "answer_text": existing,
                "citations": tuple(citations),
            }
        )
        if changed
        else payload
    )
