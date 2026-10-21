"""Split from ``release.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.bind import bind_company_atomic_links
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
from smart_rag_core.query_answer.release_literals import (
    acronym_expansion_fails,
    link_fails_literal_guard,
    release_normalize_text,
)
from smart_rag_core.query_answer.versions import PARAGRAPH_DELIMITER
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord

_GENERAL_ORIGINS = frozenset(
    {
        KnowledgeScope.GENERAL_KNOWLEDGE,
        KnowledgeScope.USER_SUPPLIED_TEXT,
        KnowledgeScope.DETERMINISTIC,
        KnowledgeScope.AMBIGUOUS,
        KnowledgeScope.WEB,
    }
)


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
        if acronym_expansion_fails(text, source_blob) and (
            ("Method Call Protocol" in text and "Method Call Protocol" not in released)
            or acronym_expansion_fails(text, released)
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
    original_spans: dict[tuple[str | None, str | None, str], list[AnswerCitation]] = {}
    for citation in (*original.citations, *original.table_citations):
        if citation.atomic_link_id is None:
            continue
        original_spans.setdefault(
            (citation.chunk_id, citation.table_id, citation.atomic_link_id), []
        ).append(citation)
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    table_citations: list[AnswerCitation] = []
    seen_passages: set[tuple[str, str, str]] = set()
    seen_tables: set[tuple[str, str]] = set()
    all_links_by_claim: dict[str, tuple[str, ...]] = {}
    for item in original.atomic_links:
        key = release_normalize_text(item.claim)
        all_links_by_claim[key] = (*all_links_by_claim.get(key, ()), item.link_id)
    for index, link in enumerate(unique_links):
        link_ids = all_links_by_claim.get(
            release_normalize_text(link.claim), (link.link_id,)
        )
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=index,
                text=re.sub(
                    r"\n{2,}",
                    "\n",
                    link.claim.replace("\r\n", "\n").replace("\r", "\n"),
                ).strip()[:4000],
                link_ids=link_ids[:6],
            )
        )
        for live in original.atomic_links:
            if live.link_id not in link_ids:
                continue
            has_owned_citations = any(
                citation.atomic_link_id == live.link_id
                and citation.chunk_id is not None
                and citation.chunk_id in passages
                and citation.span
                and citation.span in passages[citation.chunk_id].citation_text
                for citation in original.citations
            )
            for chunk_id in live.chunk_ids:
                pair = (chunk_id, None, live.link_id)
                reused_spans = original_spans.get(pair, [])
                if has_owned_citations and live.kind == "fact" and not reused_spans:
                    # Link IDs may include bookkeeping holders added by binding.
                    # They do not authorize synthesizing extra prefix citations.
                    continue
                passage = passages.get(chunk_id)
                if passage is None:
                    continue
                spans = [c.span for c in reused_spans] or [None]
                for span in spans:
                    if not span or span not in passage.citation_text:
                        span = exact_source_span(passage.citation_text)
                    if not span or (chunk_id, live.link_id, span) in seen_passages:
                        continue
                    seen_passages.add((chunk_id, live.link_id, span))
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
                if (live.table_id, live.link_id) in seen_tables:
                    continue
                seen_tables.add((live.table_id, live.link_id))
                record = tables_by_id.get(live.table_id)
                if record is None:
                    continue
                reused_spans = original_spans.get(pair, [])
                reused = reused_spans[0] if reused_spans else None
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
        if link_fails_literal_guard(item, fusion=fusion, tables=tables)
    )
    if not unsupported:
        return payload
    return drop_unsupported_paragraphs(payload, unsupported)


def render_verified_company_answer(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    user_query: str | None = None,
) -> AnswerPayload:
    """Replace free-form company prose with surviving atomic-link claims.

    Application code owns released ``answer_text``. Provider paragraph
    bodies are never copied. Citations are rebuilt from surviving links
    only; fusion passages are never backfilled.

    Args:
        payload: Answer after deterministic checks and the verifier batch.
        fusion: Fitted canonical evidence for this run.
        tables: Deterministic table snapshots.
        user_query: Original user text for multi-holder citation rebind.
            Untrusted.

    Returns:
        Payload whose prose is unique surviving claims, plus a composed
        conclusion only when every listed link survived. Citation-free
        refusal when no supported material link remains.
    """

    working = bind_company_atomic_links(payload, fusion=fusion, user_query=user_query)
    guarded = drop_ungrounded_literals(working, fusion=fusion, tables=tables)
    surviving = tuple(
        sorted(guarded.atomic_links, key=lambda item: (item.priority, item.link_id))
    )
    if not surviving:
        return citation_free_refusal(guarded)

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
            key = release_normalize_text(item.claim)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return tuple(unique)

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
