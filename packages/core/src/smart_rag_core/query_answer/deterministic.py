"""Deterministic citation, ACL, and inference-chain checks before the verifier."""

from __future__ import annotations

from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload, AtomicLink
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.query_routing.models import TableEvidenceRecord


def citation_span_aligns(span: str | None, citation_text: str) -> bool:
    """Return whether a citation span is a substring of canonical text.

    Empty citation text cannot be a whole-passage citation. Empty spans are
    whole-passage only when canonical ``raw_text`` is present.

    Args:
        span: Claimed excerpt.
        citation_text: Canonical passage text.

    Returns:
        True when canonical text is non-empty and the span is empty or
        occurs in the passage.
    """

    if not citation_text.strip():
        return False
    if span is None or span == "":
        return True
    return span in citation_text


def table_ranges_align(
    claimed: tuple[str, ...],
    provenance: tuple[str, ...],
) -> bool:
    """Return whether claimed table ranges are a subset of sandbox provenance.

    Args:
        claimed: Ranges cited by the answer.
        provenance: Exact ranges from ``TableQueryResult``.

    Returns:
        True when every claimed range is present.
    """

    if not claimed:
        return False
    allowed = set(provenance)
    return all(item in allowed for item in claimed)


def inference_chain_complete(
    links: tuple[AtomicLink, ...],
    conclusion_link_ids: tuple[str, ...],
) -> bool:
    """Return whether every conclusion link exists and cites evidence.

    Args:
        links: Atomic links from the answer.
        conclusion_link_ids: Ordered link IDs on the composed conclusion.

    Returns:
        True when each listed link exists and has passage or table evidence.
    """

    by_id = {item.link_id: item for item in links}
    for link_id in conclusion_link_ids:
        item = by_id.get(link_id)
        if item is None:
            return False
        if not item.chunk_ids and not (item.table_id and item.source_ranges):
            return False
    return True


def deterministic_check_answer(
    payload: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> tuple[AnswerPayload, tuple[str, ...]]:
    """Strip unauthorized, misaligned, or incomplete citations and links.

    Args:
        payload: Model or mock answer.
        fusion: Canonical Combined/Hybrid evidence.
        tables: Deterministic table snapshots.

    Returns:
        Filtered payload and failure reason codes. Unsupported links are
        omitted or refused, never softened into uncited claims.
    """

    passages = {item.chunk_id: item for item in fusion.evidence}
    tables_by_id = {item.table_id: item for item in tables}
    failures: list[str] = []
    kept_citations: list[AnswerCitation] = []
    for citation in (*payload.citations, *payload.table_citations):
        ok, reason = _citation_ok(citation, passages, tables_by_id)
        if ok:
            kept_citations.append(citation)
        else:
            failures.append(reason)
    kept_links: list[AtomicLink] = []
    refused: list[str] = list(payload.refused_links)
    for link in payload.atomic_links:
        if _link_supported(link, passages, tables_by_id):
            kept_links.append(link)
        else:
            refused.append(link.link_id)
            failures.append("unsupported_link")
    conclusion = payload.composed_conclusion
    if conclusion is not None:
        if not inference_chain_complete(tuple(kept_links), conclusion.link_ids):
            failures.append("unsupported_chain")
            conclusion = None
            if payload.status == "complete":
                payload = payload.model_copy(update={"status": "partial"})
    passage_citations = tuple(
        item for item in kept_citations if item.chunk_id is not None
    )
    table_citations = tuple(
        item for item in kept_citations if item.table_id is not None
    )
    status = payload.status
    if not fusion.evidence and not tables:
        status = "refused"
        failures.append("insufficient_evidence")
    elif "empty_citation_text" in failures and status == "complete":
        status = "partial"
    elif refused and status == "complete":
        status = "partial"
    return (
        payload.model_copy(
            update={
                "citations": passage_citations,
                "table_citations": table_citations,
                "atomic_links": tuple(kept_links),
                "composed_conclusion": conclusion,
                "refused_links": tuple(dict.fromkeys(refused)),
                "status": status,
            }
        ),
        tuple(dict.fromkeys(failures)),
    )


def _citation_ok(
    citation: AnswerCitation,
    passages: dict[str, ScoredPassage],
    tables: dict[str, TableEvidenceRecord],
) -> tuple[bool, str]:
    """Validate one citation against canonical evidence.

    Args:
        citation: Answer citation.
        passages: Canonical passages by chunk ID.
        tables: Table records by table ID.

    Returns:
        ``(ok, reason)``.
    """

    chunk_id = citation.chunk_id
    table_id = citation.table_id
    if chunk_id:
        passage = passages.get(chunk_id)
        if passage is None:
            return False, "unauthorized_or_missing_passage"
        if not passage.citation_text.strip():
            return False, "empty_citation_text"
        if not citation_span_aligns(citation.span, passage.citation_text):
            return False, "citation_span_mismatch"
        return True, "ok"
    if table_id:
        record = tables.get(table_id)
        if record is None:
            return False, "unauthorized_or_missing_table"
        claimed = tuple(citation.source_ranges)
        if not table_ranges_align(claimed, record.source_ranges):
            return False, "table_range_mismatch"
        return True, "ok"
    return False, "citation_without_source"


def _link_supported(
    link: AtomicLink,
    passages: dict[str, ScoredPassage],
    tables: dict[str, TableEvidenceRecord],
) -> bool:
    """Return whether an atomic link cites at least one surviving source.

    Args:
        link: Atomic claim.
        passages: Canonical passages.
        tables: Table records.

    Returns:
        True when at least one cited ID is present and authorized.
    """

    if any(chunk_id in passages for chunk_id in link.chunk_ids):
        return True
    if link.table_id and link.table_id in tables and link.source_ranges:
        return table_ranges_align(
            link.source_ranges, tables[link.table_id].source_ranges
        )
    return False
