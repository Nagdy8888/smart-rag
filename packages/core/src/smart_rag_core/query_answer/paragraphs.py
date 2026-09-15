"""Paragraph-to-citation contract for company-document answers."""

from __future__ import annotations

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_CITATIONS,
    MAX_ANSWER_PARAGRAPHS,
    MAX_CITATION_SPAN_CHARS,
    MAX_VERIFIER_LINKS,
    PARAGRAPH_DELIMITER,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.query_routing.models import TableEvidenceRecord

INSUFFICIENT_EVIDENCE_TEXT = "Insufficient authorized evidence."


def join_paragraph_text(paragraphs: tuple[AnswerParagraph, ...]) -> str:
    """Join ordered paragraph bodies into durable answer prose.

    Args:
        paragraphs: Contiguous zero-based paragraphs.

    Returns:
        ``PARAGRAPH_DELIMITER``-joined text, or empty when there are no
        paragraphs.
    """

    ordered = tuple(sorted(paragraphs, key=lambda item: item.paragraph_index))
    return PARAGRAPH_DELIMITER.join(item.text for item in ordered)


def with_derived_answer_text(payload: AnswerPayload) -> AnswerPayload:
    """Replace ``answer_text`` with joined paragraph bodies when present.

    Args:
        payload: Structured answer.

    Returns:
        Payload whose ``answer_text`` matches ordered paragraphs.
    """

    if not payload.paragraphs:
        return payload
    return payload.model_copy(
        update={"answer_text": join_paragraph_text(payload.paragraphs)}
    )


def citation_free_refusal(payload: AnswerPayload) -> AnswerPayload:
    """Return a citation-free company refusal. Original prose is dropped.

    Args:
        payload: Answer that cannot keep any grounded paragraph.

    Returns:
        Refused payload with empty paragraphs, citations, and links.
    """

    refused = tuple(
        dict.fromkeys(
            (*payload.refused_links, *(item.link_id for item in payload.atomic_links))
        )
    )
    return payload.model_copy(
        update={
            "answer_text": INSUFFICIENT_EVIDENCE_TEXT,
            "paragraphs": (),
            "citations": (),
            "table_citations": (),
            "atomic_links": (),
            "composed_conclusion": None,
            "status": "refused",
            "refused_links": refused,
        }
    )


def apply_paragraph_contract(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    required: bool,
) -> tuple[AnswerPayload, tuple[str, ...]]:
    """Validate company paragraph mappings or refuse uncited output.

    Args:
        payload: Model or mock answer after invented-ID filtering.
        fusion: Canonical Combined/Hybrid evidence.
        tables: Deterministic table snapshots.
        required: When true, empty paragraphs fail closed for live
            company answers. General, Web, and legacy payloads pass
            ``required=False``.

    Returns:
        Normalized payload and stable machine reason codes.
    """

    if not payload.paragraphs:
        if required:
            return citation_free_refusal(payload), ("paragraph_unmapped",)
        return payload, ()
    passages = {item.chunk_id: item for item in fusion.evidence}
    tables_by_id = {item.table_id: item for item in tables}
    links_by_id = {item.link_id: item for item in payload.atomic_links}
    failures: list[str] = []
    paragraphs = tuple(
        sorted(payload.paragraphs, key=lambda item: item.paragraph_index)
    )
    if len(paragraphs) > MAX_ANSWER_PARAGRAPHS:
        failures.append("answer_bounds_exceeded")
    if len(payload.atomic_links) > MAX_VERIFIER_LINKS:
        failures.append("answer_bounds_exceeded")
    citation_count = len(payload.citations) + len(payload.table_citations)
    if citation_count > MAX_ANSWER_CITATIONS:
        failures.append("answer_bounds_exceeded")
    expected = tuple(range(len(paragraphs)))
    actual = tuple(item.paragraph_index for item in paragraphs)
    if actual != expected:
        failures.append("paragraph_index_invalid")
    unique_failures = tuple(dict.fromkeys(failures))
    blocking = {"answer_bounds_exceeded", "paragraph_index_invalid"}
    if any(item in blocking for item in unique_failures):
        return citation_free_refusal(payload), unique_failures
    paragraph_by_index = {item.paragraph_index: item for item in paragraphs}
    kept_passages: list[AnswerCitation] = []
    kept_tables: list[AnswerCitation] = []
    for citation in payload.citations:
        ok, reason = _mapped_passage_ok(
            citation,
            paragraph_by_index=paragraph_by_index,
            links_by_id=links_by_id,
            passages=passages,
        )
        if ok:
            kept_passages.append(citation)
        else:
            failures.append(reason)
    for citation in payload.table_citations:
        ok, reason = _mapped_table_ok(
            citation,
            paragraph_by_index=paragraph_by_index,
            links_by_id=links_by_id,
            tables=tables_by_id,
        )
        if ok:
            kept_tables.append(citation)
        else:
            failures.append(reason)
    valid = (*kept_passages, *kept_tables)
    surviving: list[AnswerParagraph] = []
    for paragraph in paragraphs:
        if PARAGRAPH_DELIMITER in paragraph.text or not paragraph.text.strip():
            failures.append("paragraph_index_invalid")
            continue
        if not paragraph.link_ids:
            failures.append("paragraph_unmapped")
            continue
        paragraph_ok = True
        for link_id in paragraph.link_ids:
            if link_id not in links_by_id:
                failures.append("citation_link_mismatch")
                paragraph_ok = False
                continue
            matching = [
                item
                for item in valid
                if item.paragraph_index == paragraph.paragraph_index
                and item.atomic_link_id == link_id
            ]
            if not matching:
                failures.append("paragraph_unmapped")
                paragraph_ok = False
        if paragraph_ok:
            surviving.append(paragraph)
    unique_failures = tuple(dict.fromkeys(failures))
    if any(item in blocking for item in unique_failures) or not surviving:
        return citation_free_refusal(payload), unique_failures or (
            "paragraph_unmapped",
        )
    kept_indexes = {item.paragraph_index for item in surviving}
    rebuilt = _with_surviving_paragraphs(
        payload,
        surviving=tuple(surviving),
        citations=tuple(
            item for item in kept_passages if item.paragraph_index in kept_indexes
        ),
        table_citations=tuple(
            item for item in kept_tables if item.paragraph_index in kept_indexes
        ),
        extra_refused=(),
        status="partial" if unique_failures else payload.status,
    )
    return rebuilt, unique_failures


def drop_unsupported_paragraphs(
    payload: AnswerPayload,
    unsupported: frozenset[str],
) -> AnswerPayload:
    """Remove paragraphs that depend on unsupported or omitted links.

    Args:
        payload: Answer after deterministic checks.
        unsupported: Link IDs rejected or omitted by the verifier.

    Returns:
        Payload with surviving paragraphs and rebuilt ``answer_text``.
        Citation-free refusal when nothing survives.
    """

    if not unsupported:
        return payload
    if not payload.paragraphs:
        kept_links = tuple(
            item for item in payload.atomic_links if item.link_id not in unsupported
        )
        refused = tuple(dict.fromkeys((*payload.refused_links, *sorted(unsupported))))
        conclusion = payload.composed_conclusion
        if conclusion is not None and any(
            link_id in unsupported for link_id in conclusion.link_ids
        ):
            conclusion = None
        status = payload.status
        if status == "complete":
            status = "partial"
        return payload.model_copy(
            update={
                "atomic_links": kept_links,
                "composed_conclusion": conclusion,
                "refused_links": refused,
                "status": status,
            }
        )
    surviving = tuple(
        paragraph
        for paragraph in payload.paragraphs
        if not any(link_id in unsupported for link_id in paragraph.link_ids)
    )
    if not surviving:
        refused = citation_free_refusal(payload)
        extra = tuple(dict.fromkeys((*refused.refused_links, *sorted(unsupported))))
        return refused.model_copy(update={"refused_links": extra})
    kept_indexes = {item.paragraph_index for item in surviving}
    dropped = len(surviving) < len(payload.paragraphs)
    status = payload.status
    if dropped and status == "complete":
        status = "partial"
    return _with_surviving_paragraphs(
        payload,
        surviving=surviving,
        citations=tuple(
            item for item in payload.citations if item.paragraph_index in kept_indexes
        ),
        table_citations=tuple(
            item
            for item in payload.table_citations
            if item.paragraph_index in kept_indexes
        ),
        extra_refused=tuple(sorted(unsupported)),
        status=status,
        drop_conclusion_links=unsupported,
    )


def _with_surviving_paragraphs(
    payload: AnswerPayload,
    *,
    surviving: tuple[AnswerParagraph, ...],
    citations: tuple[AnswerCitation, ...],
    table_citations: tuple[AnswerCitation, ...],
    extra_refused: tuple[str, ...],
    status: str,
    drop_conclusion_links: frozenset[str] | None = None,
) -> AnswerPayload:
    """Reindex surviving paragraphs and rebuild derived answer text.

    Args:
        payload: Original answer.
        surviving: Paragraphs that still have complete citation coverage.
        citations: Passage citations owned by surviving paragraphs.
        table_citations: Table citations owned by surviving paragraphs.
        extra_refused: Additional refused link IDs.
        status: Terminal answer status.
        drop_conclusion_links: Link IDs that invalidate the conclusion.

    Returns:
        Payload with contiguous paragraph indexes and joined prose.
    """

    remapped = _reindex_paragraphs(surviving, citations, table_citations)
    referenced = {
        link_id for paragraph in remapped[0] for link_id in paragraph.link_ids
    }
    kept_links = tuple(
        item for item in payload.atomic_links if item.link_id in referenced
    )
    conclusion = payload.composed_conclusion
    dropped = drop_conclusion_links or frozenset()
    if conclusion is not None and any(
        link_id in dropped or link_id not in referenced
        for link_id in conclusion.link_ids
    ):
        conclusion = None
    refused = tuple(dict.fromkeys((*payload.refused_links, *extra_refused)))
    return with_derived_answer_text(
        payload.model_copy(
            update={
                "paragraphs": remapped[0],
                "citations": remapped[1],
                "table_citations": remapped[2],
                "atomic_links": kept_links,
                "composed_conclusion": conclusion,
                "refused_links": refused,
                "status": status,
            }
        )
    )


def _reindex_paragraphs(
    paragraphs: tuple[AnswerParagraph, ...],
    citations: tuple[AnswerCitation, ...],
    table_citations: tuple[AnswerCitation, ...],
) -> tuple[
    tuple[AnswerParagraph, ...],
    tuple[AnswerCitation, ...],
    tuple[AnswerCitation, ...],
]:
    """Rewrite surviving paragraph indexes to a contiguous 0-based range.

    Args:
        paragraphs: Surviving paragraphs in original index order.
        citations: Passage citations to remap.
        table_citations: Table citations to remap.

    Returns:
        Reindexed paragraphs and citations.
    """

    ordered = tuple(sorted(paragraphs, key=lambda item: item.paragraph_index))
    mapping = {
        paragraph.paragraph_index: index for index, paragraph in enumerate(ordered)
    }
    remapped_paragraphs = tuple(
        paragraph.model_copy(
            update={"paragraph_index": mapping[paragraph.paragraph_index]}
        )
        for paragraph in ordered
    )

    def _remap(items: tuple[AnswerCitation, ...]) -> tuple[AnswerCitation, ...]:
        """Copy citations onto the remapped paragraph indexes.

        Args:
            items: Citations owned by surviving paragraphs.

        Returns:
            Citations whose ``paragraph_index`` matches the new order.
        """

        remapped: list[AnswerCitation] = []
        for item in items:
            if item.paragraph_index not in mapping:
                continue
            remapped.append(
                item.model_copy(
                    update={"paragraph_index": mapping[item.paragraph_index]}
                )
            )
        return tuple(remapped)

    return remapped_paragraphs, _remap(citations), _remap(table_citations)


def exact_source_span(text: str) -> str:
    """Return a bounded exact span copied from canonical text.

    Args:
        text: Canonical passage or table cell text.

    Returns:
        1-1000 character substring with paragraph delimiters collapsed.
        Empty when ``text`` has no non-whitespace characters.
    """

    collapsed = " ".join(part.strip() for part in text.split(PARAGRAPH_DELIMITER))
    stripped = collapsed.strip()
    if not stripped:
        return ""
    return stripped[:MAX_CITATION_SPAN_CHARS]


def _mapped_passage_ok(
    citation: AnswerCitation,
    *,
    paragraph_by_index: dict[int, AnswerParagraph],
    links_by_id: dict[str, AtomicLink],
    passages: dict[str, ScoredPassage],
) -> tuple[bool, str]:
    """Return whether a passage citation satisfies the paragraph contract.

    Args:
        citation: Candidate passage citation.
        paragraph_by_index: Surviving paragraphs.
        links_by_id: Atomic links by id.
        passages: Fusion passages by chunk id.

    Returns:
        ``(ok, reason)``.
    """

    from smart_rag_core.query_answer.deterministic import citation_span_aligns

    if citation.paragraph_index is None:
        return False, "citation_paragraph_mismatch"
    paragraph = paragraph_by_index.get(citation.paragraph_index)
    if paragraph is None:
        return False, "citation_paragraph_mismatch"
    if (
        citation.atomic_link_id is None
        or citation.atomic_link_id not in paragraph.link_ids
    ):
        return False, "citation_link_mismatch"
    link = links_by_id.get(citation.atomic_link_id)
    if link is None:
        return False, "citation_link_mismatch"
    chunk_id = citation.chunk_id
    if chunk_id is None or chunk_id not in passages:
        return False, "unauthorized_or_missing_passage"
    if chunk_id not in link.chunk_ids:
        return False, "citation_link_mismatch"
    span = citation.span
    if span is None or not span.strip():
        return False, "citation_span_required"
    if len(span) > MAX_CITATION_SPAN_CHARS:
        return False, "answer_bounds_exceeded"
    passage = passages[chunk_id]
    if not passage.citation_text.strip():
        return False, "empty_citation_text"
    if not citation_span_aligns(span, passage.citation_text):
        return False, "citation_span_mismatch"
    return True, "ok"


def _mapped_table_ok(
    citation: AnswerCitation,
    *,
    paragraph_by_index: dict[int, AnswerParagraph],
    links_by_id: dict[str, AtomicLink],
    tables: dict[str, TableEvidenceRecord],
) -> tuple[bool, str]:
    """Return whether a table citation satisfies the paragraph contract.

    Args:
        citation: Candidate table citation.
        paragraph_by_index: Surviving paragraphs.
        links_by_id: Atomic links by id.
        tables: Table records by id.

    Returns:
        ``(ok, reason)``.
    """

    from smart_rag_core.query_answer.deterministic import table_ranges_align

    if citation.paragraph_index is None:
        return False, "citation_paragraph_mismatch"
    paragraph = paragraph_by_index.get(citation.paragraph_index)
    if paragraph is None:
        return False, "citation_paragraph_mismatch"
    if (
        citation.atomic_link_id is None
        or citation.atomic_link_id not in paragraph.link_ids
    ):
        return False, "citation_link_mismatch"
    link = links_by_id.get(citation.atomic_link_id)
    if link is None:
        return False, "citation_link_mismatch"
    table_id = citation.table_id
    if table_id is None or table_id not in tables:
        return False, "unauthorized_or_missing_table"
    if link.table_id != table_id:
        return False, "citation_link_mismatch"
    claimed = tuple(citation.source_ranges)
    if not table_ranges_align(claimed, tables[table_id].source_ranges):
        return False, "table_range_mismatch"
    if (
        claimed
        and claimed != tuple(link.source_ranges)
        and not set(claimed) <= set(link.source_ranges)
    ):
        return False, "table_range_mismatch"
    return True, "ok"
