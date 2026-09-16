"""Bind omitted company paragraphs, links, and exact citation spans."""

from __future__ import annotations

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import exact_source_span
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_CITATIONS,
    MAX_ANSWER_PARAGRAPHS,
)
from smart_rag_core.query_fusion.models import FusionResult


def bind_company_atomic_links(
    payload: AnswerPayload,
    *,
    fusion: FusionResult | None = None,
) -> AnswerPayload:
    """Fill omitted atomic links, citation ids, and exact source spans.

    Live ``answer_v3`` payloads sometimes omit paragraphs or atomic
    links, or paraphrase citation spans. Deterministic paragraph mapping
    requires those bindings and contained spans before verification.

    Args:
        payload: Company answer after invented-ID filtering.
        fusion: Fitted canonical evidence used to copy exact spans.
            Omitted when the caller only needs link synthesis.

    Returns:
        Payload with synthesized fact links, citation ``atomic_link_id``
        values, and contained spans when they can be derived.
        Unchanged when paragraphs are ungrounded.
    """

    working = payload
    if not working.paragraphs and working.atomic_links:
        working = _paragraphs_from_links(working, fusion)
    paragraphs = tuple(_paragraph_with_link_id(item) for item in working.paragraphs)
    citations = tuple(
        _citation_with_link_id(citation, paragraphs) for citation in working.citations
    )
    table_citations = tuple(
        _citation_with_link_id(citation, paragraphs)
        for citation in working.table_citations
    )
    working = working.model_copy(
        update={
            "paragraphs": paragraphs,
            "citations": citations,
            "table_citations": table_citations,
        }
    )
    if not working.atomic_links:
        synthesized = _links_from_paragraphs(working)
        if synthesized:
            working = working.model_copy(update={"atomic_links": synthesized})
    if fusion is None:
        return working
    return _align_citation_spans(working, fusion)


def _paragraphs_from_links(
    payload: AnswerPayload,
    fusion: FusionResult | None,
) -> AnswerPayload:
    """Build paragraphs and exact-span citations from omitted paragraph lists.

    Live ``answer_v3`` payloads sometimes emit atomic links without
    paragraphs. Deterministic paragraph mapping then fail-closes before
    the verifier. Claims stay owned by the links; spans are copied from
    authorized ``citation_text`` when fusion is available.

    Args:
        payload: Company answer with atomic links and empty paragraphs.
        fusion: Fitted canonical passages, or ``None`` when spans cannot
            be copied yet.

    Returns:
        Payload with one paragraph per link and contained citation spans
        for authorized chunk IDs. Unchanged when no grounded citation
        can be built.
    """

    passages = (
        {item.chunk_id: item for item in fusion.evidence} if fusion is not None else {}
    )
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    for index, link in enumerate(payload.atomic_links[:MAX_ANSWER_PARAGRAPHS]):
        claim = link.claim.strip()
        if not claim:
            continue
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=index,
                text=claim[:4000],
                link_ids=(link.link_id,),
            )
        )
        for chunk_id in link.chunk_ids:
            if len(citations) >= MAX_ANSWER_CITATIONS:
                break
            passage = passages.get(chunk_id)
            span = (
                exact_source_span(passage.citation_text) if passage is not None else ""
            )
            if passage is None or not span:
                continue
            citations.append(
                AnswerCitation(
                    chunk_id=chunk_id,
                    span=span,
                    paragraph_index=index,
                    atomic_link_id=link.link_id,
                )
            )
    if not paragraphs:
        return payload
    updates: dict[str, object] = {"paragraphs": tuple(paragraphs)}
    if citations and not payload.citations:
        updates["citations"] = tuple(citations)
    return payload.model_copy(update=updates)


def _paragraph_with_link_id(paragraph: AnswerParagraph) -> AnswerParagraph:
    """Copy a paragraph, filling a synthetic link id when omitted.

    Args:
        paragraph: Company paragraph from the model payload.

    Returns:
        The paragraph, or a copy with ``p{index}`` as its only link id.
    """

    if paragraph.link_ids:
        return paragraph
    return paragraph.model_copy(update={"link_ids": (f"p{paragraph.paragraph_index}",)})


def _align_citation_spans(
    payload: AnswerPayload,
    fusion: FusionResult,
) -> AnswerPayload:
    """Replace missing or non-substring spans with exact source excerpts.

    Args:
        payload: Company answer after link binding.
        fusion: Fitted canonical passages.

    Returns:
        Payload whose passage citation spans are empty-or-contained
        substrings of authorized ``citation_text``. Unauthorized chunk
        IDs are left unchanged for later fail-closed checks.
    """

    passages = {item.chunk_id: item for item in fusion.evidence}
    aligned: list[AnswerCitation] = []
    for citation in payload.citations:
        chunk_id = citation.chunk_id
        if chunk_id is None or chunk_id not in passages:
            aligned.append(citation)
            continue
        text = passages[chunk_id].citation_text
        span = citation.span
        if span and span in text:
            aligned.append(citation)
            continue
        replacement = exact_source_span(text)
        if not replacement:
            aligned.append(citation)
            continue
        aligned.append(citation.model_copy(update={"span": replacement}))
    return payload.model_copy(update={"citations": tuple(aligned)})


def _citation_with_link_id(
    citation: AnswerCitation,
    paragraphs: tuple[AnswerParagraph, ...],
) -> AnswerCitation:
    """Copy a citation, filling ``atomic_link_id`` from its paragraph.

    Args:
        citation: Passage or table citation.
        paragraphs: Ordered company paragraphs.

    Returns:
        The citation, or a copy with the paragraph's first link id.
    """

    if citation.atomic_link_id:
        return citation
    paragraph = next(
        (
            item
            for item in paragraphs
            if item.paragraph_index == citation.paragraph_index
        ),
        None,
    )
    if paragraph is None or not paragraph.link_ids:
        return citation
    return citation.model_copy(update={"atomic_link_id": paragraph.link_ids[0]})


def _links_from_paragraphs(payload: AnswerPayload) -> tuple[AtomicLink, ...]:
    """Build fact links from grounded paragraphs when the model omitted them.

    Args:
        payload: Company answer with paragraphs and citations.

    Returns:
        One fact link per paragraph that cites at least one passage or
        table. Empty when paragraphs cannot be grounded.
    """

    synthesized: list[AtomicLink] = []
    for paragraph in payload.paragraphs:
        chunk_ids: list[str] = []
        for citation in payload.citations:
            chunk_id = citation.chunk_id
            if (
                citation.paragraph_index != paragraph.paragraph_index
                or not chunk_id
                or chunk_id in chunk_ids
            ):
                continue
            chunk_ids.append(chunk_id)
        table_citation = next(
            (
                citation
                for citation in payload.table_citations
                if citation.paragraph_index == paragraph.paragraph_index
                and citation.table_id
            ),
            None,
        )
        if not chunk_ids and table_citation is None:
            continue
        link_id = (
            paragraph.link_ids[0]
            if paragraph.link_ids
            else f"p{paragraph.paragraph_index}"
        )
        synthesized.append(
            AtomicLink(
                link_id=link_id[:64],
                claim=paragraph.text[:2000],
                chunk_ids=tuple(chunk_ids[:12]),
                table_id=None if table_citation is None else table_citation.table_id,
                source_ranges=(
                    () if table_citation is None else table_citation.source_ranges
                ),
                kind="fact",
                priority=paragraph.paragraph_index + 1,
            )
        )
    return tuple(synthesized)
