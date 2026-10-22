"""Complete an omitted comparison side with exact fitted evidence before verification."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.generate_anchor_salvage import append_anchor_claim
from smart_rag_core.query_answer.generate_literals import significant_query_terms
from smart_rag_core.query_answer.language import requested_answer_language
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.source_focus import prioritize_answer_sources
from smart_rag_core.query_fusion.models import FusionResult

_COMPARISON = re.compile(
    r"(?i)\b(?:difference|distinction|contrast)\s+between\s+(.{1,120}?)\s+and\s+(.{1,120}?)[.!?]?$"
    r"|\bcompare\s+(.{1,120}?)\s+(?:with|versus|vs\.?|and)\s+(.{1,120}?)[.!?]?$"
)
_GENERIC = frozenset({"agent", "agents", "system", "systems", "approach", "approaches"})


def fill_comparison_coverage(
    payload: AnswerPayload, fusion: FusionResult, *, user_query: str
) -> AnswerPayload:
    """Append at most one source sentence for an entirely omitted comparison side.

    Call only on drafts. The added claim keeps exact source ownership and must
    pass the normal binder and verifier; never restore rejected model prose.
    """
    match = _COMPARISON.search(user_query)
    if (
        match is None
        or requested_answer_language(user_query) != "en"
        or not payload.atomic_links
        or len(payload.atomic_links) >= 6
        or len(payload.citations) + len(payload.table_citations) >= 12
        or len(payload.paragraphs) >= 6
        or "```" in payload.answer_text
        or "|" in payload.answer_text
    ):
        return payload
    subjects = match.groups()[:2] if match.group(1) else match.groups()[2:]
    terms = [set(significant_query_terms(subject)) - _GENERIC for subject in subjects]
    if not all(terms):
        return payload
    shown = payload.answer_text.casefold()
    covered = [
        any(re.search(rf"\b{re.escape(t)}\b", shown) for t in side) for side in terms
    ]
    if covered.count(True) != 1:
        return payload
    missing = terms[covered.index(False)]
    candidates: list[tuple[int, int, str, str]] = []
    for rank, source in enumerate(
        prioritize_answer_sources(fusion, user_query).evidence
    ):
        for sentence in re.split(r"(?<=[.!?])\s+|\n\s*\n", source.citation_text):
            sentence = sentence.strip()
            if not 60 <= len(sentence) <= 900 or sentence not in source.citation_text:
                continue
            if re.search(r"(?m)^\s*(?:#|\||```|def |class )", sentence):
                continue
            hits = sum(
                bool(re.search(rf"(?i)\b{re.escape(t)}\b", sentence)) for t in missing
            )
            if hits != len(missing):
                continue
            starts = int(
                any(re.match(rf"(?i){re.escape(t)}\b", sentence) for t in missing)
            )
            candidates.append((starts, -rank, source.chunk_id, sentence))
    if not candidates:
        return payload
    _, _, chunk_id, span = max(candidates, key=lambda item: item[:2])
    if len(payload.answer_text) + len(span) + 2 > 8000:
        return payload
    return append_anchor_claim(
        payload, chunk_id=chunk_id, span=span, link_id="query-facet-1"
    )
