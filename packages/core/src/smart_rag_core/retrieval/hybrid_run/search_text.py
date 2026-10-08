"""Question-sentence search text and reciprocal-rank merges."""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from smart_rag_core.retrieval.source_scope import strip_source_selectors

_QUESTION = re.compile(r"[^.!?]*\?")
_RRF_K = 60


def question_search_text(query: str, selectors: Sequence[str] = ()) -> str:
    """Return the question sentences, with authorized titles removed.

    Args:
        query: Full user message, including any instruction sentences.
        selectors: Authorized source titles. Other names are left in place.

    Returns:
        The sentences that end in ``?``, joined in order. The original query
        when none of those sentences remain.
    """

    pieces: list[str] = []
    for match in _QUESTION.finditer(query):
        sentence = strip_source_selectors(match.group(0).strip(), selectors)
        if sentence and sentence != query and sentence not in pieces:
            pieces.append(sentence)
    if not pieces:
        return query
    return " ".join(pieces)


def merge_variant_ranks(lists: Sequence[Sequence[UUID]]) -> tuple[UUID, ...]:
    """Merge per-variant ranked IDs with reciprocal rank.

    Args:
        lists: Dense lists, each in that variant's rank order.

    Returns:
        Distinct IDs, best combined rank first. ``rrf_k`` is 60, the frozen
        fusion constant. An ID that is first in any list outranks an ID
        that is deep in every list.
    """

    scores: dict[UUID, float] = {}
    for ranked in lists:
        for index, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + index)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], str(chunk_id)))
    return tuple(ordered)
