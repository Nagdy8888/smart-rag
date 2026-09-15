"""Citation-preview mapping without passage text."""

from __future__ import annotations

from smart_rag_core.query_answer.models import AnswerPayload


def citation_preview(
    payload: AnswerPayload,
) -> tuple[str, dict[str, object]] | None:
    """Build citation preview IDs without passage text.

    Args:
        payload: Verified answer payload.

    Returns:
        ``citation_preview`` event or None when no identifiers exist.
        Web rows contribute ``web_source_id`` values only. Span and
        excerpt text are never included.
    """

    identifiers: list[str] = []
    for citation in (*payload.citations, *payload.table_citations):
        if citation.chunk_id:
            identifiers.append(citation.chunk_id)
        elif citation.table_id:
            identifiers.append(citation.table_id)
    for citation in payload.web_citations:
        identifiers.append(citation.web_source_id)
    if not identifiers:
        return None
    ranks = tuple(range(1, len(identifiers) + 1))
    return (
        "citation_preview",
        {"citation_ids": tuple(identifiers), "ranks": ranks},
    )
