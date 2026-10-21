"""Bounded exact-source coverage for multipart questions and cited role lists."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.generate_anchor_salvage import append_anchor_claim
from smart_rag_core.query_answer.generate_literals import significant_query_terms
from smart_rag_core.query_answer.language import requested_answer_language
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.native_selection import requested_artifact_labels
from smart_rag_core.query_answer.source_focus import prioritize_answer_sources
from smart_rag_core.query_answer.table_copy import copy_pipe_table
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.retrieval.rerank import named_code_definition_ids

_LIST_ASK = re.compile(
    r"(?i)\b(?:responsibilit\w*|threats|attack types)\b|التهديدات|المسؤوليات"
)
_THREAT_ASK = re.compile(r"(?i)\b(?:threats|attack types)\b|التهديدات|أنواع الهجمات")
_THREAT_HEADER = re.compile(r"(?im)^\s*\|\s*(?:attack|threat)(?:\s+type)?\s*\|")
_FACET_STOP = frozenset({"across", "lets", "does", "should", "which", "their"})


def narrative_claim_limit(query: str, source_records: str) -> int:
    """Reserve half of six slots for an explicitly requested category table.

    Args:
        query: Original question.
        source_records: Already fitted canonical records, used only for shape.

    Returns:
        Three prose claims when a requested category matrix is present, else six.
    """
    return (
        3 if _THREAT_ASK.search(query) and _THREAT_HEADER.search(source_records) else 6
    )


def salvage_question_coverage(
    payload: AnswerPayload, fusion: FusionResult, *, user_query: str
) -> AnswerPayload:
    """Fill a missing explicit question part or copy a table from a cited source.

    Only already fitted canonical text is eligible. No model prose is restored,
    no context grows, and all existing paragraphs and citation ownership survive.

    Args:
        payload: Generated or checked answer, before citation persistence.
        fusion: Authorized fitted evidence.
        user_query: Original user text.

    Returns:
        Exact-source additions within existing limits, or the original payload.
    """
    if (
        named_code_definition_ids(user_query)
        or requested_artifact_labels(user_query, "table")
        or requested_artifact_labels(user_query, "figure")
    ):
        return payload
    working = _fill_explicit_facets(payload, fusion, user_query)
    if _LIST_ASK.search(user_query):
        working = _append_cited_table(working, fusion, user_query)
    return working


def _fill_explicit_facets(
    payload: AnswerPayload, fusion: FusionResult, query: str
) -> AnswerPayload:
    """Copy one short paragraph for an uncovered explicit second question."""
    if requested_answer_language(query) != "en":
        return payload
    parts = re.split(r"(?i)\band\s+(?:what|how|why|which|where|when)\b", query)
    if len(parts) != 2:
        return payload
    terms = tuple(t for t in significant_query_terms(parts[1]) if t not in _FACET_STOP)
    shown = payload.answer_text.casefold()
    missing = tuple(t for t in terms if not re.search(rf"\b{re.escape(t)}", shown))
    if not missing:
        return payload
    candidates: list[tuple[int, int, str, str]] = []
    for source in prioritize_answer_sources(fusion, parts[1]).evidence:
        for paragraph in re.split(r"\n\s*\n", source.citation_text):
            if (
                not 40 <= len(paragraph) <= 1000
                or paragraph not in source.citation_text
            ):
                continue
            hits = sum(
                bool(re.search(rf"(?i)\b{re.escape(t)}", paragraph)) for t in terms
            )
            new = sum(
                bool(re.search(rf"(?i)\b{re.escape(t)}", paragraph)) for t in missing
            )
            if hits >= 2 and new:
                candidates.append((new, hits, source.chunk_id, paragraph))
    if not candidates:
        return payload
    _, _, chunk, span = max(candidates, key=lambda c: (c[1], c[0]))
    filled = append_anchor_claim(
        payload, chunk_id=chunk, span=span, link_id="query-facet-2"
    )
    return (
        filled.model_copy(update={"status": "partial"})
        if filled is not payload
        else payload
    )


def _append_cited_table(
    payload: AnswerPayload, fusion: FusionResult, query: str
) -> AnswerPayload:
    """Keep a cited table or an explicitly requested category-header match."""
    if not payload.paragraphs:
        return payload
    if any(
        link.link_id.startswith(("cited-table-", "table-block-"))
        for link in payload.atomic_links
    ):
        return payload
    used = {c.chunk_id for c in payload.citations}
    for source in prioritize_answer_sources(fusion, query).evidence:
        category_match = bool(
            _THREAT_ASK.search(query) and _THREAT_HEADER.search(source.citation_text)
        )
        if source.chunk_id not in used and not category_match:
            continue
        copied = copy_pipe_table(payload, source, caption="")
        if copied is None or copied.answer_text in payload.answer_text:
            continue
        offset = max((p.paragraph_index for p in payload.paragraphs), default=-1) + 1
        if (
            offset + len(copied.paragraphs) > 6
            or len(payload.atomic_links) + len(copied.atomic_links) > 6
            or len(payload.citations) + len(copied.citations) > 12
            or len(payload.answer_text) + len(copied.answer_text) + 2 > 8000
        ):
            return payload.model_copy(update={"status": "partial"})
        ids = {
            link.link_id: f"cited-table-{i + 1}"
            for i, link in enumerate(copied.atomic_links)
        }
        paragraphs = tuple(
            p.model_copy(
                update={
                    "paragraph_index": offset + i,
                    "link_ids": tuple(ids[link_id] for link_id in p.link_ids),
                }
            )
            for i, p in enumerate(copied.paragraphs)
        )
        links = tuple(
            link.model_copy(update={"link_id": ids[link.link_id]})
            for link in copied.atomic_links
        )
        citations = tuple(
            c.model_copy(
                update={
                    "paragraph_index": offset + (c.paragraph_index or 0),
                    "atomic_link_id": ids[c.atomic_link_id or ""],
                }
            )
            for c in copied.citations
        )
        return payload.model_copy(
            update={
                "answer_text": payload.answer_text + "\n\n" + copied.answer_text,
                "paragraphs": (*payload.paragraphs, *paragraphs),
                "atomic_links": (*payload.atomic_links, *links),
                "citations": (*payload.citations, *citations),
                "status": "partial" if copied.status != "complete" else payload.status,
            }
        )
    return payload
