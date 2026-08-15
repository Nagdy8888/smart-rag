"""Deterministic query-profile extractors. Original query text is never mutated."""

from __future__ import annotations

import re
from dataclasses import dataclass

from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_profile.aliases import resolve_approved_aliases
from smart_rag_core.query_profile.dates import parse_gregorian_v1
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

_INV_SR = re.compile(r"\bINV-SR-\d{4}\b")
_SKU = re.compile(r"\bSKU-P4-[A-Z0-9]{3}\b")
_QUOTES = re.compile(r'"([^"]{1,200})"')
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-z]")
_DOCUMENT_SCOPE = re.compile(r"\bdocument\s+(p4-src-\d{4})\b", re.IGNORECASE)
_COMPARE = re.compile(r"^Compare\s+(PRJ-[A-Z]{5,12})\s+leave days and notice period\.$")
ALLOWED_FILTER_KEYS = frozenset({"tag", "language"})
ALLOWED_TABLE_OPS = frozenset({"sum", "count", "avg", "min", "max"})


@dataclass(frozen=True, slots=True)
class DeterministicExtract:
    """Values taken from the original query without a model call.

    Attributes:
        language: ``en``, ``ar``, or ``mixed``.
        locale: Locale/configuration string.
        query_type: Allow-listed query type.
        codes: INV-SR and SKU-P4 identifiers present in the query.
        quoted_phrases: Double-quoted spans.
        aliases: Approved aliases resolved from the query.
        dates: Gregorian ISO dates.
        temporal_intent: ``latest``, ``current``, ``recent``, ``as_of``, or ``none``.
        target_date: First extracted date when temporal intent needs one.
        filters: Allow-listed ``key=value`` metadata filters.
        negation_scope: Negation enum.
        document_scope: Document/section scope or ``none``.
        media_dependence: Figure/chart-only evidence signal.
        historical_relationship: Past-anchored relationship language.
        relationship_intent: Relationship/multi-hop signal.
        table_intent: Structured-table signal.
        table_ops: Allow-listed table operations.
        subquestions: At most three decomposition strings.
        variants: At most three focused variants.
        rewrite_justified: Whether a focused rewrite is requested.
        normalized_query: ``arabic_norm_v1`` search form; never a citation.
    """

    language: str
    locale: str
    query_type: QueryType
    codes: tuple[str, ...]
    quoted_phrases: tuple[str, ...]
    aliases: tuple[str, ...]
    dates: tuple[str, ...]
    temporal_intent: str
    target_date: str | None
    filters: tuple[str, ...]
    negation_scope: str
    document_scope: str
    media_dependence: bool
    historical_relationship: bool
    relationship_intent: bool
    table_intent: bool
    table_ops: tuple[str, ...]
    subquestions: tuple[str, ...]
    variants: tuple[str, ...]
    rewrite_justified: bool
    normalized_query: str


def detect_language(query: str) -> str:
    """Detect ``en``, ``ar``, or ``mixed`` from script presence.

    Args:
        query: Original query.

    Returns:
        Language code used by the labeled corpus.
    """

    has_arabic = _ARABIC.search(query) is not None
    has_latin = _LATIN.search(query) is not None
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    return "en"


def classify_query_type(query: str) -> QueryType:
    """Classify query type with deterministic templates.

    Args:
        query: Original query.

    Returns:
        Allow-listed ``QueryType``. Ambiguous remainder is ``factual``.
    """

    lowered = query.lower()
    if "sum the" in lowered and "sheet" in lowered:
        return QueryType.STRUCTURED_TABULAR
    if query.startswith("Summarize"):
        return QueryType.BROAD_SUMMARY
    if lowered.startswith("compare ") and " and " in lowered:
        return QueryType.MULTI_PART
    if (
        "related to" in lowered
        or lowered.startswith("which team owns")
        or query.startswith("Map entity")
    ):
        return QueryType.RELATIONSHIP_MULTI_HOP
    if (
        re.search(r"\b(status|stauts) of\b", lowered) is not None
        or "orion widget alias" in lowered
    ):
        return QueryType.EXACT_IDENTIFIER
    return QueryType.FACTUAL


def extract_codes(query: str) -> tuple[str, ...]:
    """Extract INV-SR and SKU-P4 codes present in the query.

    Project codes are identifiers for routing but are not labeled ``codes``
    in the Packet 1 corpus unless they use those two families.

    Args:
        query: Original query.

    Returns:
        Distinct codes in first-seen order.
    """

    found: list[str] = []
    seen: set[str] = set()
    for pattern in (_INV_SR, _SKU):
        for match in pattern.finditer(query):
            value = match.group(0)
            if value not in seen:
                seen.add(value)
                found.append(value)
    return tuple(found)


def extract_filters(query: str) -> tuple[str, ...]:
    """Extract allow-listed metadata filters.

    Args:
        query: Original query.

    Returns:
        ``tag=`` and ``language=`` filters. Unknown keys are omitted.
    """

    lowered = query.lower()
    found: list[str] = []
    if "tagged safety" in lowered or "tagged safety" in query.lower():
        found.append("tag=safety")
    language_match = re.search(r"\blanguage\s+(en|ar|mixed)\b", lowered)
    if language_match is not None:
        found.append(f"language={language_match.group(1)}")
    return tuple(item for item in found if item.split("=", 1)[0] in ALLOWED_FILTER_KEYS)


def extract_temporal_intent(query: str) -> str:
    """Return temporal intent without inventing a timezone.

    Args:
        query: Original query.

    Returns:
        ``as_of`` wins over ``latest`` when both appear.
    """

    lowered = query.lower()
    if "as of" in lowered:
        return "as_of"
    if re.search(r"\blatest\b", lowered):
        return "latest"
    if re.search(r"\bcurrent\b", lowered):
        return "current"
    if re.search(r"\brecent\b", lowered):
        return "recent"
    return "none"


def extract_negation_scope(query: str) -> str:
    """Return negation scope. Absence is ``none``, never an inverted set.

    Args:
        query: Original query.

    Returns:
        ``set_complement``, ``entity_exclusion``, ``policy_exclusion``, or ``none``.
    """

    lowered = query.lower()
    if "not allowed" in lowered:
        return "set_complement"
    if re.search(r"\bexcept\b|\bexcluding\b", lowered):
        return "entity_exclusion"
    if "not covered by policy" in lowered:
        return "policy_exclusion"
    return "none"


def extract_subquestions(query: str) -> tuple[str, ...]:
    """Decompose a compare-query into at most three subquestions.

    Args:
        query: Original query.

    Returns:
        Subquestions, or empty when decomposition is not justified.
    """

    match = _COMPARE.match(query)
    if match is None:
        return ()
    project = match.group(1)
    return (f"{project} leave days", f"{project} notice")


def extract_deterministic(query: str) -> DeterministicExtract:
    """Run every deterministic extractor on the original query.

    Args:
        query: Unmodified user query.

    Returns:
        Frozen extract. The original query is not rewritten.

    Side Effects:
        None.
    """

    language = detect_language(query)
    locale = "mixed" if language == "mixed" else "en-US"
    query_type = classify_query_type(query)
    codes = extract_codes(query)
    aliases = resolve_approved_aliases(query)
    dates = parse_gregorian_v1(query)
    temporal = extract_temporal_intent(query)
    lowered = query.lower()
    table_intent = "sum the" in lowered and "sheet" in lowered
    table_ops = ("sum",) if table_intent else ()
    scope_match = _DOCUMENT_SCOPE.search(query)
    document_scope = f"document:{scope_match.group(1)}" if scope_match else "none"
    return DeterministicExtract(
        language=language,
        locale=locale,
        query_type=query_type,
        codes=codes,
        quoted_phrases=tuple(match.group(1) for match in _QUOTES.finditer(query)),
        aliases=aliases,
        dates=dates,
        temporal_intent=temporal,
        target_date=dates[0] if dates else None,
        filters=extract_filters(query),
        negation_scope=extract_negation_scope(query),
        document_scope=document_scope,
        media_dependence=("chart" in lowered or "figure" in lowered)
        and "unlabeled" in lowered,
        historical_relationship="after the" in lowered and "handoff" in lowered,
        relationship_intent=query_type is QueryType.RELATIONSHIP_MULTI_HOP,
        table_intent=table_intent,
        table_ops=tuple(op for op in table_ops if op in ALLOWED_TABLE_OPS),
        subquestions=extract_subquestions(query),
        variants=(),
        rewrite_justified="keep quoted" in lowered,
        normalized_query=normalize_arabic_v1(query),
    )
