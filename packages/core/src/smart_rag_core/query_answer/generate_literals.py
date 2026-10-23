"""Split from ``generate_grounded.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerPayload,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.models import TableEvidenceRecord

_NUMBER_LITERAL = re.compile(r"\b\d+(?:[.,]\d+)?\b")

_HYPHEN_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")

_WORD_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

_PROPER_NAME_TOKEN = re.compile(r"\b[A-Z][A-Za-z0-9_+./-]{2,}\b")

_STOP_LITERALS = frozenset(
    {
        "2",
        "4",
        "5",
        "about",
        "agents",
        "and",
        "answer",
        "applications",
        "building",
        "company",
        "document",
        "does",
        "explain",
        "figure",
        "from",
        "give",
        "how",
        "many",
        "name",
        "only",
        "page",
        "section",
        "that",
        "the",
        "use",
        "using",
        "what",
        "with",
        "wording",
        "words",
    }
)

# Book-title tokens appear in every company Ask prompt for this corpus and
# must never be treated as passage anchors (they match almost any page).
_BOOK_TITLE_NAME_STOP = frozenset(
    {
        "agents",
        "ai",
        "applications",
        "building",
        "designing",
        "implementing",
        "multiagent",
        "systems",
    }
)


def distinctive_query_names(user_query: str) -> tuple[str, ...]:
    """Extract capitalized product/name tokens from the user question.

    Exact-wording asks often name the target entity without numerals. Those
    names are strong passage anchors when they already appear in selected
    evidence. Tokens in ``_BOOK_TITLE_NAME_STOP`` are excluded.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Deduplicated proper-name tokens in encounter order.
    """

    found: list[str] = []
    seen: set[str] = set()
    for match in _PROPER_NAME_TOKEN.finditer(user_query):
        token = match.group(0)
        key = token.casefold()
        if key in _STOP_LITERALS or key in _BOOK_TITLE_NAME_STOP or key in seen:
            continue
        # Skip title-case sentence starters that are ordinary English.
        if key in {
            "give",
            "in",
            "table",
            "the",
            "use",
            "what",
            "when",
            "which",
            "with",
        }:
            continue
        seen.add(key)
        found.append(token)
    return tuple(found)


def significant_query_terms(user_query: str) -> tuple[str, ...]:
    """Return content tokens from the question for evidence overlap.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Lowercased tokens of length at least three, excluding stop words.
    """

    found: list[str] = []
    seen: set[str] = set()
    for match in _WORD_TOKEN.finditer(user_query.lower()):
        token = match.group(0)
        if token in _STOP_LITERALS or token in seen:
            continue
        seen.add(token)
        found.append(token)
    return tuple(found)


def has_usable_company_evidence(
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


def claim_text_corpus(payload: AnswerPayload) -> str:
    """Join claim and paragraph text for missing-figure checks.

    Args:
        payload: Current company answer.

    Returns:
        Lowercased corpus of answer, claims, and paragraphs with dash
        spacing normalized.
    """

    parts = [payload.answer_text]
    parts.extend(link.claim for link in payload.atomic_links)
    parts.extend(paragraph.text for paragraph in payload.paragraphs)
    return _normalize_figure_key("\n".join(parts))


def is_empty_refusal(payload: AnswerPayload) -> bool:
    """Return whether the model produced no releasable company claims.

    Args:
        payload: Structured answer after invented-ID filtering.

    Returns:
        True when there are no atomic links and no paragraphs to release.
    """

    if payload.atomic_links or payload.paragraphs:
        return False
    return payload.status == "refused" or not payload.answer_text.strip()


def _normalize_figure_key(figure: str) -> str:
    """Collapse dash spacing so nearby figure spellings compare equal.

    Args:
        figure: Extracted figure substring.

    Returns:
        Lowercased key with spaces around dashes removed.
    """

    return re.sub(r"\s*([\u2013\-\u2212\u2014])\s*", r"\1", figure.lower())


def distinctive_query_literals(user_query: str) -> tuple[str, ...]:
    """Extract answer-shaped literals from the user question.

    Numbers, decimals, and hyphenated identifiers are distinctive enough
    to salvage a model refusal when they already appear in selected evidence.

    Args:
        user_query: Original user text. Untrusted.

    Returns:
        Deduplicated literals in encounter order. Empty when none qualify.
    """

    found: list[str] = []
    seen: set[str] = set()
    for match in _NUMBER_LITERAL.finditer(user_query):
        token = match.group(0)
        if token.lower() in _STOP_LITERALS:
            continue
        if len(token.replace(".", "").replace(",", "")) < 2:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(token)
    for match in _HYPHEN_TOKEN.finditer(user_query):
        token = match.group(0)
        key = token.lower()
        if key in seen or key in _STOP_LITERALS:
            continue
        seen.add(key)
        found.append(token)
    return tuple(found)


def passage_query_overlap(query: str, text: str) -> int:
    """Count distinctive query tokens (length ≥4) present in ``text``.

    Args:
        query: Original user query. Untrusted.
        text: Passage citation text.

    Returns:
        Non-negative overlap count.
    """

    if not query or not text:
        return 0
    lowered = text.lower()
    seen: set[str] = set()
    score = 0
    for match in _WORD_TOKEN.finditer(query.lower()):
        token = match.group(0)
        if len(token) < 4 or token in _STOP_LITERALS or token in seen:
            continue
        seen.add(token)
        if token in lowered:
            score += 1
    return score
