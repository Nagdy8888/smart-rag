"""Split from ``bind.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

from smart_rag_core.query_answer.bind_definitions import (
    leaf_in_evidence,
    rebind_named_definitions,
)
from smart_rag_core.query_answer.bind_prose import rebind_high_coverage_prose
from smart_rag_core.query_answer.bind_tokens import rebind_unique_claim_tokens
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
    MAX_CITATION_SPAN_CHARS,
)
from smart_rag_core.query_fusion.models import FusionResult


def bind_company_atomic_links(
    payload: AnswerPayload,
    *,
    fusion: FusionResult | None = None,
    user_query: str | None = None,
) -> AnswerPayload:
    """Fill omitted atomic links, citation ids, and exact source spans.

    Four evidence-preserving repairs run before the paragraph contract:

    - A parent citation whose span sits inside exactly one nested evidence
      chunk is retargeted to that leaf.
    - A citation whose ``atomic_link_id`` is missing or not one of its
      paragraph's link ids takes the paragraph's first link id.
    - A fact claim that names one function defined in exactly one other
      fused chunk is moved onto that chunk. The claim and span become
      the exact definition text, including a leading decorator.
    - A fact claim whose distinctive snake-case token or short verbatim
      phrase sits in fused evidence is retargeted onto up to two holding
      chunks (prose naming first for identifiers) when the current
      citation misses the preferred holder.
    - A fact whose whitespace-collapsed claim is already contained in a
      fitted passage is cited on the shortest such passage, with an exact
      raw slice of that passage. That replaces a shorter token span.
    - Each atomic link's ``chunk_ids`` gains the chunks its citations
      already cite, capped at 12.

    None of these repairs can add a chunk id that is not already in the
    fused evidence the paragraph contract will check verbatim.

    Args:
        payload: Company answer after invented-ID filtering.
        fusion: Fitted canonical evidence used to copy exact spans.
            Omitted when the caller only needs link synthesis.
        user_query: Original user text. Used only to notice a code
            request when the answer has a single fact claim. Untrusted.

    Returns:
        Payload with synthesized fact links, citation ``atomic_link_id``
        values, contained spans, and repaired link chunk lists.
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
        return _repair_link_chunk_ids(working)
    aligned = _align_citation_spans(working, fusion)
    rebound = rebind_named_definitions(aligned, fusion, user_query=user_query)
    token_bound = rebind_unique_claim_tokens(rebound, fusion, user_query=user_query)
    contained = rebind_contained_claims(token_bound, fusion)
    return _repair_link_chunk_ids(rebind_high_coverage_prose(contained, fusion))


def _collapse_bounds(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace and record the raw index of each kept character.

    Args:
        text: Passage or claim text.

    Returns:
        Collapsed text and the raw index of each character in it. A
        joining space uses the index of the whitespace run it replaced.
    """

    collapsed: list[str] = []
    raw_of: list[int] = []
    gap_start: int | None = None
    for index, char in enumerate(text):
        if char.isspace():
            if collapsed and gap_start is None:
                gap_start = index
            continue
        if gap_start is not None:
            collapsed.append(" ")
            raw_of.append(gap_start)
            gap_start = None
        collapsed.append(char)
        raw_of.append(index)
    return "".join(collapsed), raw_of


def _exact_claim_slice(text: str, claim: str) -> str:
    """Return the raw passage slice whose collapsed text is ``claim``.

    Args:
        text: Canonical passage text.
        claim: Whitespace-collapsed fact claim.

    Returns:
        Exact substring of ``text``, capped at ``MAX_CITATION_SPAN_CHARS``.
        Empty when ``claim`` is not in the collapsed passage.
    """

    collapsed, raw_of = _collapse_bounds(text)
    start = collapsed.find(claim)
    if start < 0 or not claim:
        return ""
    end = start + len(claim) - 1
    raw_start = raw_of[start]
    raw_end = raw_of[end] + 1
    return text[raw_start:raw_end][:MAX_CITATION_SPAN_CHARS]


def rebind_contained_claims(
    payload: AnswerPayload,
    fusion: FusionResult,
) -> AnswerPayload:
    """Cite the fitted passage that already contains a fact claim.

    Token rebind can leave a long claim attached to a short span in a
    different chunk. When the collapsed claim sits in a fitted passage,
    the link and its passage citation move to the shortest such passage.
    The visible claim text stays as written.

    Args:
        payload: Company answer after token rebind.
        fusion: Fitted canonical evidence.

    Returns:
        Payload with contained facts retargeted, or ``payload`` when no
        fact claim is contained in a fitted passage.
    """

    holders: dict[str, tuple[str, str]] = {}
    for link in payload.atomic_links:
        if link.kind != "fact":
            continue
        claim = " ".join(link.claim.split())
        if not claim:
            continue
        matches: list[tuple[int, str, str]] = []
        for passage in fusion.evidence:
            span = _exact_claim_slice(passage.citation_text, claim)
            if not span:
                continue
            matches.append((len(passage.citation_text), passage.chunk_id, span))
        if not matches:
            continue
        matches.sort()
        _length, chunk_id, span = matches[0]
        already = tuple(link.chunk_ids) == (chunk_id,) and any(
            citation.atomic_link_id == link.link_id
            and citation.chunk_id == chunk_id
            and citation.span == span
            for citation in payload.citations
        )
        if already:
            continue
        holders[link.link_id] = (chunk_id, span)
    if not holders:
        return payload
    links = tuple(
        link.model_copy(update={"chunk_ids": (holders[link.link_id][0],)})
        if link.link_id in holders
        else link
        for link in payload.atomic_links
    )
    citations: list[AnswerCitation] = []
    placed: set[str] = set()
    for citation in payload.citations:
        link_id = citation.atomic_link_id
        if link_id in holders and citation.chunk_id:
            if link_id in placed:
                continue
            chunk_id, span = holders[link_id]
            citations.append(
                citation.model_copy(update={"chunk_id": chunk_id, "span": span})
            )
            placed.add(link_id)
            continue
        citations.append(citation)
    for link_id, (chunk_id, span) in holders.items():
        if link_id in placed:
            continue
        paragraph_index = next(
            (
                item.paragraph_index
                for item in payload.paragraphs
                if link_id in item.link_ids
            ),
            0,
        )
        citations.append(
            AnswerCitation(
                chunk_id=chunk_id,
                span=span,
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
    return payload.model_copy(
        update={"atomic_links": links, "citations": tuple(citations)}
    )


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


def _citation_with_link_id(
    citation: AnswerCitation,
    paragraphs: tuple[AnswerParagraph, ...],
) -> AnswerCitation:
    """Copy a citation, filling ``atomic_link_id`` from its paragraph.

    Args:
        citation: Passage or table citation.
        paragraphs: Ordered company paragraphs.

    Returns:
        The citation, or a copy whose ``atomic_link_id`` is the
        paragraph's first link id when it was missing or not one of the
        paragraph's links.
    """

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
    if citation.atomic_link_id and citation.atomic_link_id in paragraph.link_ids:
        return citation
    return citation.model_copy(update={"atomic_link_id": paragraph.link_ids[0]})


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
        if span and span.strip() in passages[chunk_id].section_path:
            # A repeated section label has no claim-local content and can map
            # to several leaves. Use the following exact source paragraph;
            # ordinary grounding still verifies the claim against this source.
            at = text.find(span)
            if at >= 0:
                body = text[at + len(span) :].lstrip()
                # PDF extraction may repeat the chapter heading. Advance past
                # those identical standalone lines before choosing body text.
                while body:
                    first, _, rest = body.partition("\n")
                    if first.strip() != span.strip():
                        break
                    body = rest.lstrip()
                replacement = exact_source_span(body)
                if replacement and replacement in text:
                    span = replacement
        if not (span and span in text):
            replacement = exact_source_span(text)
            if not replacement:
                aligned.append(citation)
                continue
            span = replacement
        leaf = leaf_in_evidence(chunk_id, span, passages)
        update: dict[str, object] = {"span": span}
        if leaf is not None:
            update["chunk_id"] = leaf
        aligned.append(citation.model_copy(update=update))
    return payload.model_copy(update={"citations": tuple(aligned)})


def _repair_link_chunk_ids(payload: AnswerPayload) -> AnswerPayload:
    """Extend each link's ``chunk_ids`` with the chunks its citations cite.

    The paragraph contract rejects a citation whose chunk is not listed on
    its link. Citations are the stronger signal because their spans are
    checked verbatim against authorized passages; links are bookkeeping.
    The cap of 12 matches the link synthesis slice in this module.

    Args:
        payload: Company answer after link-id binding and span alignment.

    Returns:
        Payload whose links list every cited chunk, capped at 12 per link.
        Unchanged when nothing was missing.
    """

    cited: dict[str, list[str]] = {}
    for citation in payload.citations:
        if not citation.atomic_link_id or not citation.chunk_id:
            continue
        bucket = cited.setdefault(citation.atomic_link_id, [])
        if citation.chunk_id not in bucket:
            bucket.append(citation.chunk_id)
    changed = False
    links: list[AtomicLink] = []
    for link in payload.atomic_links:
        missing = [
            chunk_id
            for chunk_id in cited.get(link.link_id, [])
            if chunk_id not in link.chunk_ids
        ]
        if not missing:
            links.append(link)
            continue
        changed = True
        merged = (*link.chunk_ids, *missing)[:12]
        links.append(link.model_copy(update={"chunk_ids": merged}))
    if not changed:
        return payload
    return payload.model_copy(update={"atomic_links": tuple(links)})
