"""Canonical-evidence term matching for Hybrid coverage."""

from __future__ import annotations

from smart_rag_core.retrieval.hybrid_run.types import EvidenceUnit
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


def matched_terms_from_units(
    required: tuple[str, ...],
    evidence: tuple[EvidenceUnit, ...],
) -> tuple[str, ...]:
    """Return required terms found in canonical citation text and headings.

    Args:
        required: Profile exact terms, codes, phrases, entities, aliases.
        evidence: Final selected citation units.

    Returns:
        Required terms whose normalized form appears in raw text or headings.
        BM25 snippets are never consulted.
    """

    haystack = " ".join(
        normalize_arabic_v1(item.citation_text)
        + " "
        + " ".join(normalize_arabic_v1(part) for part in item.locator.section_path)
        for item in evidence
    )
    matched: list[str] = []
    seen: set[str] = set()
    for term in required:
        normalized = normalize_arabic_v1(term)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        if normalized in haystack or key in haystack.casefold():
            seen.add(key)
            matched.append(term)
    return tuple(matched)


def supported_subquestion_count(
    *,
    subquestions: tuple[str, ...],
    evidence: tuple[EvidenceUnit, ...],
    matched_terms: tuple[str, ...],
    rerank_indices: tuple[int, ...],
) -> int:
    """Count subquestions proven by rerank indices or canonical evidence.

    Args:
        subquestions: At most three profile subquestions.
        evidence: Final selected units.
        matched_terms: Required terms found in those units.
        rerank_indices: Validated indices from a completed rerank, else empty.

    Returns:
        Supported subquestion count. Identity/failure fallback is
        conservative and never invents model support.
    """

    bound = tuple(subquestions[:3])
    if rerank_indices:
        allowed = set(range(len(bound) or 1))
        return len({index for index in rerank_indices if index in allowed})
    haystack = " ".join(normalize_arabic_v1(item.citation_text) for item in evidence)
    if not bound:
        return 1 if haystack and matched_terms else 0
    matched_fold = {item.casefold() for item in matched_terms}
    supported = 0
    for sub in bound:
        tokens = [
            token for token in normalize_arabic_v1(sub).split() if len(token) >= 3
        ]
        if tokens and all(token in haystack for token in tokens):
            supported += 1
            continue
        if any(term in sub.casefold() for term in matched_fold):
            supported += 1
    return supported
