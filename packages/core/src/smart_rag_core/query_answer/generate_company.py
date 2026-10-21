"""Split from ``generate_grounded.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

from collections.abc import Callable

from smart_rag_core.query_answer.assembly import (
    assemble_source_records,
    company_input_bound_payload,
    fit_source_records,
)
from smart_rag_core.query_answer.generate_anchor_salvage import (
    salvage_anchor_claim_fill,
)
from smart_rag_core.query_answer.generate_code_salvage import (
    salvage_named_code_definition,
    salvage_named_table_block,
)
from smart_rag_core.query_answer.generate_literals import (
    has_usable_company_evidence,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
)
from smart_rag_core.query_answer.ownership_shape import shape_ownership_matrix_draft
from smart_rag_core.query_answer.paragraphs import (
    exact_source_span,
    join_paragraph_text,
    with_derived_answer_text,
)
from smart_rag_core.query_answer.query_coverage import salvage_question_coverage
from smart_rag_core.query_answer.release import bind_company_atomic_links
from smart_rag_core.query_answer.sanitize import empty_no_retrieval, filter_invented_ids
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_PARAGRAPHS,
    MAX_VERIFIER_LINKS,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord

AnswerCaller = Callable[
    [str, FusionResult, tuple[TableEvidenceRecord, ...]], AnswerPayload
]


def mock_answer_payload(
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    *,
    user_query: str,
) -> AnswerPayload:
    """Build a deterministic fixture answer that cites supplied evidence IDs.

    This is mock-mode output, not a live company-knowledge claim. Table
    values are copied, never recalculated from prose. Each paragraph maps
    to exact spans copied from canonical ``citation_text``.

    Args:
        fusion: Canonical evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text.

    Returns:
        Structured answer citing at most six passages/tables with
        paragraph mappings.
    """

    del user_query
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    table_citations: list[AnswerCitation] = []
    links: list[AtomicLink] = []
    for index, item in enumerate(fusion.evidence, start=1):
        if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
            break
        if len(links) >= MAX_VERIFIER_LINKS:
            break
        span = exact_source_span(item.citation_text)
        if not span:
            continue
        paragraph_index = len(paragraphs)
        link_id = f"link-{index}"
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=span[:4000],
                link_ids=(link_id,),
            )
        )
        citations.append(
            AnswerCitation(
                chunk_id=item.chunk_id,
                span=span,
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
        links.append(
            AtomicLink(
                link_id=link_id,
                claim=span[:400] or f"Canonical passage {item.chunk_id}",
                chunk_ids=(item.chunk_id,),
                kind="inference_link" if item.statement_ids else "fact",
                priority=index,
            )
        )
    for index, item in enumerate(tables, start=1):
        if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
            break
        if len(links) >= MAX_VERIFIER_LINKS:
            break
        paragraph_index = len(paragraphs)
        link_id = f"table-{index}"
        body = (
            exact_source_span(f"{item.operation} {item.source_ranges} {item.rows}")
            or item.operation[:4000]
        )
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=paragraph_index,
                text=body or item.operation,
                link_ids=(link_id,),
            )
        )
        table_citations.append(
            AnswerCitation(
                table_id=item.table_id,
                source_ranges=item.source_ranges,
                atomic_link_id=link_id,
                paragraph_index=paragraph_index,
            )
        )
        links.append(
            AtomicLink(
                link_id=link_id,
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
    joined = join_paragraph_text(tuple(paragraphs))
    status: str = "complete" if joined else "partial"
    return AnswerPayload(
        answer_text=joined[:8000] or "Insufficient authorized evidence.",
        paragraphs=tuple(paragraphs),
        citations=tuple(citations),
        atomic_links=tuple(links),
        composed_conclusion=conclusion,
        table_citations=tuple(table_citations),
        status="complete" if status == "complete" else "partial",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


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

    if not has_usable_company_evidence(fusion, tables):
        return empty_no_retrieval(
            "Insufficient authorized evidence.",
            status="refused",
            origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )
    fit = fit_source_records(
        user_query=user_query,
        fusion=fusion,
        tables=tables,
        max_input_chars=32_768,
        route=fusion.effective_route,
    )
    if fit.trim_reason == "input_bound_exceeded":
        return company_input_bound_payload()
    fusion = fit.fusion
    tables = fit.tables
    records = assemble_source_records(fusion, tables)
    if caller is None:
        payload = mock_answer_payload(fusion, tables, user_query=user_query)
    else:
        payload = caller(records, fusion, tables)
    payload = shape_ownership_matrix_draft(payload, fusion, user_query=user_query)
    filtered = bind_company_atomic_links(
        filter_invented_ids(payload, fusion, tables),
        fusion=fusion,
        user_query=user_query,
    )
    derived = with_derived_answer_text(filtered)
    for salvage_fn in (
        salvage_named_code_definition,
        salvage_named_table_block,
        salvage_question_coverage,
        salvage_anchor_claim_fill,
    ):
        salvaged = salvage_fn(derived, fusion, user_query=user_query)
        if salvaged is derived:
            continue
        filtered = bind_company_atomic_links(
            filter_invented_ids(salvaged, fusion, tables),
            fusion=fusion,
            user_query=user_query,
        )
        derived = with_derived_answer_text(filtered)
    return derived.model_copy(
        update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
    )
