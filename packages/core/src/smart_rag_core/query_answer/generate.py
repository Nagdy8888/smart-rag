"""One counted answer generation from canonical passages and table values."""

from __future__ import annotations

from collections.abc import Callable

from smart_rag_core.query_answer.assembly import (
    allowed_chunk_ids,
    allowed_table_ids,
    assemble_source_records,
)
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerPayload,
    AtomicLink,
    ComposedConclusion,
)
from smart_rag_core.query_answer.versions import MAX_ANSWER_GENERATIONS
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.query_routing.signals import is_greeting, is_product_help

AnswerCaller = Callable[
    [str, FusionResult, tuple[TableEvidenceRecord, ...]], AnswerPayload
]


def generate_answer(
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
    user_query: str,
    caller: AnswerCaller | None,
    already_generated: int,
    company_claim_forbidden: bool,
    graph_as_answer_forbidden: bool,
) -> AnswerPayload:
    """Generate one evidence answer or a safe no-retrieval chat response.

    Args:
        fusion: Combined or Hybrid-effective evidence.
        tables: Deterministic table snapshots.
        user_query: Original user text. Untrusted.
        caller: Structured answer adapter. None uses the extractive mock.
        already_generated: Existing answer count. A second call fails.
        company_claim_forbidden: True for NoRetrieval. Greetings and product
            help receive deterministic non-company responses; other requests
            are refused.
        graph_as_answer_forbidden: True for graph-only inspection.

    Returns:
        Structured answer citing only supplied IDs, or an uncited
        non-company response for supported NoRetrieval chat intents.

    Raises:
        AnswerError: A second answer generation was requested.
    """

    if already_generated >= MAX_ANSWER_GENERATIONS:
        raise AnswerError("second_answer_generation")
    if graph_as_answer_forbidden:
        return AnswerPayload(
            answer_text="Graph inspection cannot answer from graph leads.",
            status="refused",
        )
    if company_claim_forbidden:
        if is_greeting(user_query):
            return AnswerPayload(
                answer_text=(
                    "Hi! I'm ready to help. Ask me a question about your uploaded "
                    "documents, and I'll answer from the authorized evidence."
                ),
                status="complete",
            )
        if is_product_help(user_query):
            return AnswerPayload(
                answer_text=(
                    "I can answer questions about your authorized documents, "
                    "compare documented facts, and show the supporting sources."
                ),
                status="complete",
            )
        return AnswerPayload(
            answer_text="No company-knowledge claim is authorized for this query.",
            status="refused",
        )
    if not fusion.evidence and not tables:
        return AnswerPayload(
            answer_text="Insufficient authorized evidence.",
            status="refused",
        )
    records = assemble_source_records(fusion, tables)
    if caller is None:
        payload = mock_answer_payload(fusion, tables, user_query=user_query)
    else:
        payload = caller(records, fusion, tables)
    return filter_invented_ids(payload, fusion, tables)


def filter_invented_ids(
    payload: AnswerPayload,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Drop citations and links that invent IDs not in supplied evidence.

    Args:
        payload: Model or mock answer.
        fusion: Canonical evidence.
        tables: Table snapshots.

    Returns:
        Payload citing only supplied IDs. Citations with ``chunk_id is None``
        are dropped unless ``table_id`` is in allowed table IDs.
    """

    chunks = allowed_chunk_ids(fusion)
    table_ids = allowed_table_ids(tables)
    citations = tuple(
        item
        for item in payload.citations
        if _citation_has_allowed_source(item, chunks, table_ids)
    )
    table_citations = tuple(
        item
        for item in payload.table_citations
        if item.table_id is not None and item.table_id in table_ids
    )
    links = tuple(
        item.model_copy(
            update={
                "chunk_ids": tuple(
                    chunk_id for chunk_id in item.chunk_ids if chunk_id in chunks
                )
            }
        )
        for item in payload.atomic_links
        if (
            not item.chunk_ids or any(chunk_id in chunks for chunk_id in item.chunk_ids)
        )
        or (item.table_id is not None and item.table_id in table_ids)
    )
    return payload.model_copy(
        update={
            "citations": citations,
            "table_citations": table_citations,
            "atomic_links": links,
        }
    )


def _citation_has_allowed_source(
    item: AnswerCitation,
    chunks: frozenset[str],
    table_ids: frozenset[str],
) -> bool:
    """Return whether a citation names an allowed passage or table.

    Citations with ``chunk_id is None`` survive only when ``table_id`` is in
    supplied table IDs.

    Args:
        item: Candidate citation.
        chunks: Canonical chunk IDs from fusion.
        table_ids: Canonical table IDs from sandbox composition.

    Returns:
        True when the citation is grounded in supplied evidence.
    """

    if item.chunk_id is not None:
        return item.chunk_id in chunks
    return item.table_id is not None and item.table_id in table_ids


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
    )
