"""Grounded company-document generation and extractive mock answers."""

from __future__ import annotations

from collections.abc import Callable

from smart_rag_core.query_answer.assembly import assemble_source_records
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
)
from smart_rag_core.query_answer.sanitize import empty_no_retrieval, filter_invented_ids
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord


def _has_usable_company_evidence(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> bool:
    """Return whether grounded generation has citable company evidence.

    Fusion rows with empty ``citation_text`` are not usable: the live model
    can invent prose while the Sources tab stays empty.

    Args:
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.

    Returns:
        True when at least one passage has non-empty citation text or a
        table snapshot is present.
    """

    if tables:
        return True
    return any(item.citation_text.strip() for item in fusion.evidence)


AnswerCaller = Callable[
    [str, FusionResult, tuple[TableEvidenceRecord, ...]], AnswerPayload
]


def generate_grounded_answer(
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    user_query: str,
    caller: AnswerCaller | None,
) -> AnswerPayload:
    """Generate one company-document answer from canonical evidence.

    Args:
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text. Untrusted.
        caller: Structured RAG answer adapter. None uses the extractive mock.

    Returns:
        Structured answer citing only supplied IDs.

    Raises:
        None. Empty evidence, or fusion rows with empty citation text and
        no tables, is a typed company refusal.
    """

    if not _has_usable_company_evidence(fusion, tables):
        return empty_no_retrieval(
            "Insufficient authorized evidence.",
            status="refused",
            origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )
    records = assemble_source_records(fusion, tables)
    if caller is None:
        payload = mock_answer_payload(fusion, tables, user_query=user_query)
    else:
        payload = caller(records, fusion, tables)
    filtered = filter_invented_ids(payload, fusion, tables)
    return filtered.model_copy(
        update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
    )


def mock_answer_payload(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    *,
    user_query: str,
) -> AnswerPayload:
    """Build a deterministic fixture answer that cites supplied evidence IDs.

    This is mock-mode output, not a live company-knowledge claim. Table
    values are copied, never recalculated from prose.

    Args:
        fusion: Canonical evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text.

    Returns:
        Structured answer citing every supplied passage and table range.
    """

    del user_query
    citations = tuple(
        AnswerCitation(
            chunk_id=item.chunk_id, span=None, atomic_link_id=f"link-{index}"
        )
        for index, item in enumerate(fusion.evidence, start=1)
    )
    table_citations = tuple(
        AnswerCitation(
            table_id=item.table_id,
            source_ranges=item.source_ranges,
            atomic_link_id=f"table-{index}",
        )
        for index, item in enumerate(tables, start=1)
    )
    links: list[AtomicLink] = [
        AtomicLink(
            link_id=f"link-{index}",
            claim=item.citation_text[:400] or f"Canonical passage {item.chunk_id}",
            chunk_ids=(item.chunk_id,),
            kind="inference_link" if item.statement_ids else "fact",
            priority=index,
        )
        for index, item in enumerate(fusion.evidence, start=1)
    ]
    for index, item in enumerate(tables, start=1):
        links.append(
            AtomicLink(
                link_id=f"table-{index}",
                claim=item.operation,
                table_id=item.table_id,
                source_ranges=item.source_ranges,
                kind="fact",
                priority=100 + index,
            )
        )
    conclusion = None
    inference_ids = tuple(
        item.link_id for item in links if item.kind == "inference_link"
    )
    if len(inference_ids) >= 2:
        conclusion = ComposedConclusion(
            text="Composed multi-hop inference from the cited atomic links.",
            kind="inference",
            link_ids=inference_ids,
        )
    prose_parts = [
        item.citation_text.strip()
        for item in fusion.evidence
        if item.citation_text.strip()
    ]
    for item in tables:
        prose_parts.append(f"{item.operation} {item.source_ranges} {item.rows}")
    status: str = "complete" if prose_parts else "partial"
    return AnswerPayload(
        answer_text=" ".join(prose_parts)[:8000] or "Insufficient authorized evidence.",
        citations=citations,
        atomic_links=tuple(links),
        composed_conclusion=conclusion,
        table_citations=table_citations,
        status="complete" if status == "complete" else "partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
