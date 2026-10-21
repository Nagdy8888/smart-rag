"""Keep explicit scoped responsibility assignments in their canonical matrix."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.generate_literals import significant_query_terms
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.source_focus import prioritize_answer_sources
from smart_rag_core.query_answer.table_copy import copy_pipe_table
from smart_rag_core.query_fusion.models import FusionResult

_OWNERSHIP = re.compile(r"(?i)\b(?:responsibilit\w*|owns?|ownership|duties)\b")
_MATRIX = re.compile(r"(?i)\b(?:RACI|responsibility assignment matrix)\b")
_GENERIC = frozenset(
    {
        "which",
        "each",
        "role",
        "roles",
        "team",
        "teams",
        "agent",
        "belong",
        "belongs",
        "responsibility",
        "responsibilities",
        "owns",
        "own",
        "ownership",
        "duties",
    }
)


def shape_ownership_matrix_draft(
    payload: AnswerPayload, fusion: FusionResult, *, user_query: str
) -> AnswerPayload:
    """Shape an unverified draft for a specifically scoped ownership question.

    Args:
        payload: Fresh model or extractive draft, before any verification.
        fusion: Already authorized and fitted canonical evidence.
        user_query: Original question with at least two specific scope terms.

    Returns:
        An exact responsibility matrix when its source matches every scope term,
        otherwise the original draft. Never call this on a verified answer.
    """
    if not _OWNERSHIP.search(user_query):
        return payload
    scope = tuple(t for t in significant_query_terms(user_query) if t not in _GENERIC)
    if len(scope) < 2:
        return payload
    candidates: list[AnswerPayload] = []
    for source in prioritize_answer_sources(fusion, user_query).evidence:
        text = source.citation_text
        if not _MATRIX.search(text) or not all(
            re.search(rf"(?i)\b{re.escape(term)}\b", text) for term in scope
        ):
            continue
        # Only a role assignment matrix is eligible, not a neighboring table.
        header = re.search(r"(?m)^\s*\|[^\n]*\n\s*\|[\s|:\-]+$", text)
        if header is None or not _MATRIX.search(
            text[max(0, header.start() - 500) : header.start()]
        ):
            continue
        copied = copy_pipe_table(payload, source, caption="")
        if copied is not None:
            candidates.append(copied)
    # A page continuation may repeat the caption while containing only a few
    # rows. Prefer the fullest fitted matrix, retaining source order on ties.
    return max(candidates, key=lambda item: len(item.answer_text), default=payload)
