"""Recover a numbered diagram from exact fitted source text after an empty refusal."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.generate_literals import (
    is_empty_refusal,
    significant_query_terms,
)
from smart_rag_core.query_answer.language import requested_answer_language
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.native_selection import (
    relevant_native_fusion,
    requested_artifact_labels,
)
from smart_rag_core.query_fusion.models import FusionResult


def salvage_named_figure(
    payload: AnswerPayload, fusion: FusionResult, *, user_query: str
) -> AnswerPayload:
    """Quote a uniquely requested figure and a matching explanatory paragraph.

    Only empty company refusals are eligible. There must be one numbered request,
    one exact matching figure, and a same-version prose paragraph explicitly naming
    it with at least two topical query terms. No model claim or conclusion survives.
    English-only copying avoids passing off English source text as a translation.
    A recovered result remains partial and uses two exact bounded source spans.
    """
    labels = requested_artifact_labels(user_query, "figure")
    if not is_empty_refusal(payload) or len(labels) != 1:
        return payload
    if requested_answer_language(user_query) != "en":
        return payload
    selected = relevant_native_fusion(payload, fusion, user_query)
    figures = [
        x for x in selected.evidence if x.content_kind == "figure" and x.figure_id
    ]
    if len(figures) != 1:
        return payload
    figure = figures[0]
    chapter, number = next(iter(labels))
    label = re.compile(rf"(?i)\bFigure\s+{chapter}\s*[-\u2013]\s*{number}\b")
    terms = tuple(
        t.casefold()
        for t in significant_query_terms(user_query)
        if len(t) >= 4
        and t.casefold() not in {"figure", "include", "explain", "diagram", "show"}
    )
    candidates: list[tuple[int, str, str]] = []
    for source in fusion.evidence:
        if source.version_id != figure.version_id or source.content_kind is not None:
            continue
        for paragraph in re.split(r"\n\s*\n", source.citation_text):
            paragraph = paragraph.strip()
            if not 80 <= len(paragraph) <= 1000 or not label.search(paragraph):
                continue
            hits = sum(t in paragraph.casefold() for t in terms)
            if hits >= 2:
                candidates.append((hits, source.chunk_id, paragraph))
    caption = figure.citation_text.strip()
    if not candidates or not 1 <= len(caption) <= 1000:
        return payload
    _, chunk, prose = max(candidates, key=lambda c: (c[0], len(c[2])))
    paragraphs = (
        AnswerParagraph(paragraph_index=0, text=prose, link_ids=("figure-source-1",)),
        AnswerParagraph(
            paragraph_index=1,
            text=f"{caption}\n[[figure:{figure.figure_id}]]",
            link_ids=("figure-source-2",),
        ),
    )
    links = tuple(
        AtomicLink(link_id=f"figure-source-{i + 1}", claim=text, chunk_ids=(cid,))
        for i, (cid, text) in enumerate(((chunk, prose), (figure.chunk_id, caption)))
    )
    citations = tuple(
        AnswerCitation(
            chunk_id=link.chunk_ids[0],
            span=link.claim,
            atomic_link_id=link.link_id,
            paragraph_index=i,
        )
        for i, link in enumerate(links)
    )
    return payload.model_copy(
        update={
            "answer_text": "\n\n".join(p.text for p in paragraphs),
            "paragraphs": paragraphs,
            "atomic_links": links,
            "citations": citations,
            "composed_conclusion": None,
            "status": "partial",
        }
    )
