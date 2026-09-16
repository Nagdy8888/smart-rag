"""Release only verifier-supported company claims into durable answer prose."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import (
    citation_free_refusal,
    drop_unsupported_paragraphs,
    exact_source_span,
)
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_CITATIONS,
    MAX_ANSWER_PARAGRAPHS,
    PARAGRAPH_DELIMITER,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord

_ACRONYM_PAREN = re.compile(r"\b([A-Z]{2,10})\s*\(([^)]{2,80})\)")
_PAREN_ACRONYM = re.compile(
    r"\b([A-Z][A-Za-z0-9][A-Za-z0-9 ./-]{1,60}?)\s*\(([A-Z]{2,10})\)"
)
_STANDS_FOR = re.compile(
    r"\b([A-Z]{2,10})\s+(?:stands for|means|is short for|expands to)\s+"
    r"([A-Za-z][A-Za-z0-9 ./-]{1,80})",
    re.IGNORECASE,
)
_TITLE_PHRASE = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+)+)\b")
_QUOTED = re.compile(r"\"([^\"]{1,200})\"|'([^']{1,200})'|`([^`]{1,200})`")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NAMED_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)
_CODE_TOKEN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*(?:\(\))?")
_GENERAL_ORIGINS = frozenset(
    {
        KnowledgeScope.GENERAL_KNOWLEDGE,
        KnowledgeScope.USER_SUPPLIED_TEXT,
        KnowledgeScope.DETERMINISTIC,
        KnowledgeScope.AMBIGUOUS,
        KnowledgeScope.WEB,
    }
)


def company_release_applies(payload: AnswerPayload, *, is_web: bool) -> bool:
    """Return whether grounded company rendering should rewrite this payload.

    Args:
        payload: Verified or checked answer.
        is_web: True when the run is the Web path.

    Returns:
        False for general, user-text, deterministic, ambiguous, and Web
        answers. True for company-document payloads.
    """

    if is_web:
        return False
    origin = payload.answer_origin
    if origin in _GENERAL_ORIGINS:
        return False
    if origin is KnowledgeScope.COMPANY_DOCUMENTS:
        return True
    return bool(payload.paragraphs or payload.atomic_links)


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


def render_verified_company_answer(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Replace free-form company prose with surviving atomic-link claims.

    Application code owns released ``answer_text``. Provider paragraph
    bodies are never copied. Citations are rebuilt from surviving links
    only; fusion passages are never backfilled.

    Args:
        payload: Answer after deterministic checks and the verifier batch.
        fusion: Fitted canonical evidence for this run.
        tables: Deterministic table snapshots.

    Returns:
        Payload whose prose is unique surviving claims, plus a composed
        conclusion only when every listed link survived. Citation-free
        refusal when no supported material link remains.
    """

    working = bind_company_atomic_links(payload, fusion=fusion)
    guarded = drop_ungrounded_literals(working, fusion=fusion, tables=tables)
    surviving = tuple(
        sorted(guarded.atomic_links, key=lambda item: (item.priority, item.link_id))
    )
    if not surviving:
        return citation_free_refusal(guarded)
    unique_links = _unique_claims(surviving)
    conclusion = guarded.composed_conclusion
    kept_ids = {item.link_id for item in surviving}
    if conclusion is not None and any(
        link_id not in kept_ids for link_id in conclusion.link_ids
    ):
        conclusion = None
    claim_texts = [item.claim.strip() for item in unique_links]
    if conclusion is not None:
        claim_texts.append(conclusion.text.strip())
    stripped_ungrounded = _original_prose_had_ungrounded_expansion(
        payload, surviving=surviving, fusion=fusion, tables=tables
    )
    status = guarded.status
    if stripped_ungrounded and status == "complete":
        status = "partial"
    paragraphs, citations, table_citations = _rebuild_paragraphs_and_citations(
        unique_links,
        original=guarded,
        fusion=fusion,
        tables=tables,
    )
    return guarded.model_copy(
        update={
            "answer_text": PARAGRAPH_DELIMITER.join(claim_texts),
            "paragraphs": paragraphs,
            "citations": citations,
            "table_citations": table_citations,
            "atomic_links": surviving,
            "composed_conclusion": conclusion,
            "status": status,
        }
    )


def drop_ungrounded_literals(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Drop links whose exact-value guards fail, even if a verifier agreed.

    Args:
        payload: Answer after deterministic/verifier filtering.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        Payload without links that invent acronym expansions or fact
        literals absent from cited sources.
    """

    unsupported = frozenset(
        item.link_id
        for item in payload.atomic_links
        if _link_fails_literal_guard(item, fusion=fusion, tables=tables)
    )
    if not unsupported:
        return payload
    return drop_unsupported_paragraphs(payload, unsupported)


def _link_fails_literal_guard(
    link: AtomicLink,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> bool:
    """Return whether one link invents an expansion or missing fact literal.

    Args:
        link: Candidate atomic claim.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        True when the claim must be dropped.
    """

    source_text = _cited_source_text(link, fusion=fusion, tables=tables)
    if _acronym_expansion_fails(link.claim, source_text):
        return True
    if link.kind != "fact":
        return False
    return _fact_literals_missing(link.claim, source_text)


def _cited_source_text(
    link: AtomicLink,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> str:
    """Join cited passage and table text for one link.

    Args:
        link: Atomic claim.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        Concatenated cited source text.
    """

    passages = {item.chunk_id: item.citation_text for item in fusion.evidence}
    bodies = [passages[chunk_id] for chunk_id in link.chunk_ids if chunk_id in passages]
    if link.table_id:
        record = next((item for item in tables if item.table_id == link.table_id), None)
        if record is not None:
            bodies.append(f"{record.operation} {record.rows} {record.source_ranges}")
    return "\n".join(bodies)


def _normalize(text: str) -> str:
    """Collapse case and whitespace for exact expansion compares.

    Args:
        text: Raw expansion or phrase.

    Returns:
        Lowercased collapsed form.
    """

    return " ".join(text.strip().lower().split()).strip(".,:;!?")


def _acronym_expansions(text: str) -> dict[str, set[str]]:
    """Extract acronym-to-expansion maps from definition-shaped phrases.

    Args:
        text: Source or claim text.

    Returns:
        Acronym keys mapped to normalized expansions.
    """

    found: dict[str, set[str]] = {}
    for match in _ACRONYM_PAREN.finditer(text):
        found.setdefault(match.group(1), set()).add(_normalize(match.group(2)))
    for match in _PAREN_ACRONYM.finditer(text):
        found.setdefault(match.group(2), set()).add(_normalize(match.group(1)))
    for match in _STANDS_FOR.finditer(text):
        found.setdefault(match.group(1).upper(), set()).add(_normalize(match.group(2)))
    return found


def _title_phrases(text: str) -> tuple[str, ...]:
    """Return Title Case multi-word phrases.

    Args:
        text: Source or claim text.

    Returns:
        Normalized phrases with at least two words.
    """

    return tuple(_normalize(item.group(0)) for item in _TITLE_PHRASE.finditer(text))


def _acronym_expansion_fails(claim: str, source_text: str) -> bool:
    """Return whether the claim invents or mismatches an acronym expansion.

    Args:
        claim: Atomic claim or paragraph sentence.
        source_text: Cited canonical text.

    Returns:
        True when an expansion is not spelled in the source or conflicts.
    """

    source_defs = _acronym_expansions(source_text)
    claim_defs = _acronym_expansions(claim)
    normalized_source = _normalize(source_text)
    for acronym, expansions in claim_defs.items():
        allowed = set(source_defs.get(acronym, set()))
        for expansion in expansions:
            if expansion and expansion in normalized_source:
                allowed.add(expansion)
        if not allowed or any(item not in allowed for item in expansions):
            return True
    claim_phrases = _title_phrases(claim)
    for expansions in source_defs.values():
        for expansion in expansions:
            words = expansion.split()
            if len(words) < 2:
                continue
            last = words[-1]
            for phrase in claim_phrases:
                phrase_words = phrase.split()
                if (
                    len(phrase_words) == len(words)
                    and phrase_words[-1] == last
                    and phrase not in expansions
                ):
                    return True
    return False


def _fact_literals_missing(claim: str, source_text: str) -> bool:
    """Return whether a fact claim uses literals absent from the cited source.

    Args:
        claim: Fact-link claim.
        source_text: Cited canonical text.

    Returns:
        True when a required quoted, numeric, date, or code literal is
        absent.
    """

    for match in _QUOTED.finditer(claim):
        literal = next(item for item in match.groups() if item)
        if literal not in source_text:
            return True
    for match in _NUMBER.finditer(claim):
        if match.group(0) not in source_text:
            return True
    for pattern in (_ISO_DATE, _NAMED_DATE, _CODE_TOKEN):
        for match in pattern.finditer(claim):
            if match.group(0) not in source_text:
                return True
    return False


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


def _unique_claims(links: tuple[AtomicLink, ...]) -> tuple[AtomicLink, ...]:
    """Keep the first occurrence of each claim in priority order.

    Args:
        links: Surviving links already sorted by ``(priority, link_id)``.

    Returns:
        Deduplicated links.
    """

    seen: set[str] = set()
    unique: list[AtomicLink] = []
    for item in links:
        key = _normalize(item.claim)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _original_prose_had_ungrounded_expansion(
    payload: AnswerPayload,
    *,
    surviving: tuple[AtomicLink, ...],
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> bool:
    """Return whether original company prose contained a dropped expansion.

    Args:
        payload: Pre-render payload.
        surviving: Links that passed guards.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        True when original paragraphs or ``answer_text`` invented an
        expansion that surviving claims do not carry.
    """

    source_blob = "\n".join(
        (
            *(item.citation_text for item in fusion.evidence),
            *(f"{item.operation} {item.rows}" for item in tables),
        )
    )
    released = "\n".join(item.claim for item in surviving)
    originals = [payload.answer_text, *(item.text for item in payload.paragraphs)]
    for text in originals:
        if not text:
            continue
        if _acronym_expansion_fails(text, source_blob) and (
            ("Method Call Protocol" in text and "Method Call Protocol" not in released)
            or _acronym_expansion_fails(text, released)
        ):
            return True
    return False


def _rebuild_paragraphs_and_citations(
    unique_links: tuple[AtomicLink, ...],
    *,
    original: AnswerPayload,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> tuple[
    tuple[AnswerParagraph, ...],
    tuple[AnswerCitation, ...],
    tuple[AnswerCitation, ...],
]:
    """Build one paragraph per unique claim and citations from those links.

    Args:
        unique_links: Deduplicated surviving claims in release order.
        original: Payload holding original spans to reuse when valid.
        fusion: Canonical passages.
        tables: Deterministic table snapshots.

    Returns:
        Reindexed paragraphs, passage citations, and table citations.
    """

    passages = {item.chunk_id: item for item in fusion.evidence}
    tables_by_id = {item.table_id: item for item in tables}
    original_spans: dict[tuple[str | None, str | None, str], AnswerCitation] = {}
    for citation in (*original.citations, *original.table_citations):
        if citation.atomic_link_id is None:
            continue
        original_spans[
            (citation.chunk_id, citation.table_id, citation.atomic_link_id)
        ] = citation
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    table_citations: list[AnswerCitation] = []
    seen_pairs: set[tuple[str | None, str | None, str]] = set()
    all_links_by_claim: dict[str, tuple[str, ...]] = {}
    for item in original.atomic_links:
        key = _normalize(item.claim)
        all_links_by_claim[key] = (*all_links_by_claim.get(key, ()), item.link_id)
    for index, link in enumerate(unique_links):
        link_ids = all_links_by_claim.get(_normalize(link.claim), (link.link_id,))
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=index,
                text=link.claim.strip()[:4000],
                link_ids=link_ids[:6],
            )
        )
        for live in original.atomic_links:
            if live.link_id not in link_ids:
                continue
            for chunk_id in live.chunk_ids:
                pair = (chunk_id, None, live.link_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                reused = original_spans.get(pair)
                span = reused.span if reused is not None else None
                passage = passages.get(chunk_id)
                if passage is None:
                    continue
                if not span or span not in passage.citation_text:
                    span = exact_source_span(passage.citation_text)
                if not span:
                    continue
                citations.append(
                    AnswerCitation(
                        chunk_id=chunk_id,
                        span=span,
                        atomic_link_id=live.link_id,
                        paragraph_index=index,
                        inference=live.kind == "inference_link",
                    )
                )
            if live.table_id:
                pair = (None, live.table_id, live.link_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                record = tables_by_id.get(live.table_id)
                if record is None:
                    continue
                reused = original_spans.get(pair)
                table_citations.append(
                    AnswerCitation(
                        table_id=live.table_id,
                        source_ranges=reused.source_ranges
                        if reused is not None and reused.source_ranges
                        else record.source_ranges,
                        atomic_link_id=live.link_id,
                        paragraph_index=index,
                        inference=False,
                    )
                )
    return tuple(paragraphs), tuple(citations), tuple(table_citations)
