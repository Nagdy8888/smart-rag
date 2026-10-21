"""Present already fitted evidence by coverage of the original question."""

from __future__ import annotations

import math
import re

from smart_rag_core.query_answer.source_terms import answer_focus_terms
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


def prioritize_answer_sources(fusion: FusionResult, query: str) -> FusionResult:
    """Order fitted records by distinctive query coverage, without changing them.

    Retrieval rank alone can put several broad neighboring-topic passages ahead
    of the passage containing the question's narrower process or second facet.
    This presentation pass retains every authorized fitted record and its rank.
    It neither retrieves nor expands context and makes no support decision.

    Args:
        fusion: Already fitted canonical evidence under the input ceiling.
        query: Original user question, never an abbreviated retrieval rewrite.

    Returns:
        Evidence permutation with unchanged contents, or the original object.
    """
    terms = answer_focus_terms(query)
    if len(terms) < 2 or len(fusion.evidence) < 2:
        return fusion
    patterns = [re.compile(rf"\b{re.escape(term)}", re.I) for term in terms]
    hits = [
        tuple(
            bool(pattern.search(normalize_arabic_v1(item.citation_text)))
            for pattern in patterns
        )
        for item in fusion.evidence
    ]
    weights = [
        math.log1p(len(hits) / (1 + sum(row[i] for row in hits)))
        for i in range(len(terms))
    ]
    scores = [
        sum(w for w, hit in zip(weights, row, strict=True) if hit) for row in hits
    ]
    heading_scores = [
        sum(
            weight
            for weight, pattern in zip(weights, patterns, strict=True)
            if pattern.search(normalize_arabic_v1(" ".join(item.section_path)))
        )
        for item in fusion.evidence
    ]
    indices = sorted(
        range(len(hits)), key=lambda i: (-scores[i], -heading_scores[i], i)
    )
    if indices == list(range(len(hits))):
        return fusion
    return fusion.model_copy(
        update={"evidence": tuple(fusion.evidence[i] for i in indices)}
    )
