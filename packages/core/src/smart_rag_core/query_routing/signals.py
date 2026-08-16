"""Phase 6 packet 2 intent detectors. Frozen Phase 4 extract is not mutated."""

from __future__ import annotations

import re

from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_profile.extract import DeterministicExtract

_GREETING = re.compile(
    r"^(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b",
    re.IGNORECASE,
)
_PRODUCT_HELP = re.compile(
    r"\b(how do i use this (app|product)|what can you do|help me use the (app|product))\b",
    re.IGNORECASE,
)
_TRANSFORM = re.compile(
    r"^(rewrite|rephrase|translate|summarize this text)\b",
    re.IGNORECASE,
)
_GRAPH_INSPECT = re.compile(
    r"\b(inspect (the )?(current )?graph|show (the )?graph|graph explorer|"
    r"list entities in (the )?workspace|graph inspection)\b",
    re.IGNORECASE,
)
_CORPUS_THEME = re.compile(
    r"\b(corpus-wide|across (the )?(corpus|knowledge base)|"
    r"landscape of|company-wide theme)\b",
    re.IGNORECASE,
)
_WHOLE_DOC = re.compile(
    r"\b(entire|whole|full)\s+document\b|\bsummarize (the |this )?document\b",
    re.IGNORECASE,
)
_PAST_REL = re.compile(
    r"\b(previously|in the past|last year|historically|after the|as of)\b",
    re.IGNORECASE,
)
_REL_HINT = re.compile(
    r"\b(related to|depends on|impact of|connection between|who owns|"
    r"multi-hop|which team owns)\b",
    re.IGNORECASE,
)
_LOW_CONF_REL = re.compile(
    r"\b(maybe related|might be connected|possibly depends)\b",
    re.IGNORECASE,
)
_CAPTION_OCR = re.compile(r"\b(caption|ocr text|alt text)\b", re.IGNORECASE)


def is_no_retrieval(query: str) -> bool:
    """Return whether the query is greeting, product help, or user-text transform.

    Args:
        query: Original user text.

    Returns:
        True when company retrieval must not run.
    """

    stripped = query.strip()
    return (
        _GREETING.search(stripped) is not None
        or _PRODUCT_HELP.search(stripped) is not None
        or _TRANSFORM.search(stripped) is not None
    )


def is_graph_inspection(query: str) -> bool:
    """Return whether the user asked for explicit graph inspection.

    Args:
        query: Original user text.

    Returns:
        True when GraphOnlyInspection is the only allowed family.
    """

    return _GRAPH_INSPECT.search(query) is not None


def is_corpus_wide_theme(query: str) -> bool:
    """Return whether the query asks for a corpus landscape/theme.

    Args:
        query: Original user text.

    Returns:
        True when Combined global steering plus Hybrid is required.
    """

    return _CORPUS_THEME.search(query) is not None


def is_whole_document_summary(query: str, extract: DeterministicExtract) -> bool:
    """Return whether this is a single-document whole summary.

    Args:
        query: Original user text.
        extract: Deterministic Phase 4 extract.

    Returns:
        True when ``section_coverage_ratio=1.0`` is required to answer.
    """

    if extract.query_type is not QueryType.BROAD_SUMMARY:
        return False
    if extract.document_scope != "none":
        return True
    return _WHOLE_DOC.search(query) is not None


def is_historical_relationship(query: str, extract: DeterministicExtract) -> bool:
    """Return whether a relationship/multi-hop signal is past or ``as_of``.

    Args:
        query: Original user text.
        extract: Deterministic Phase 4 extract.

    Returns:
        True when Hybrid plus ``temporal_graph_limitation`` is required.
    """

    if extract.historical_relationship:
        return True
    if not (extract.relationship_intent or _REL_HINT.search(query)):
        return False
    if extract.temporal_intent == "as_of":
        return True
    return _PAST_REL.search(query) is not None


def is_low_confidence_relationship(query: str, extract: DeterministicExtract) -> bool:
    """Return whether a weak relationship signal should start on Hybrid.

    Args:
        query: Original user text.
        extract: Deterministic Phase 4 extract.

    Returns:
        True when Hybrid starts and the signal is retained for correction.
    """

    if _LOW_CONF_REL.search(query) is not None:
        return True
    if extract.relationship_intent:
        return False
    return _REL_HINT.search(query) is not None


def is_current_relationship(query: str, extract: DeterministicExtract) -> bool:
    """Return whether a current relationship/multi-hop should select Combined.

    Args:
        query: Original user text.
        extract: Deterministic Phase 4 extract.

    Returns:
        True when Combined is the matrix family, not historical Hybrid.
    """

    if is_historical_relationship(query, extract):
        return False
    if is_low_confidence_relationship(query, extract):
        return False
    if extract.relationship_intent:
        return True
    return extract.query_type is QueryType.RELATIONSHIP_MULTI_HOP


def media_has_caption_or_ocr(query: str) -> bool:
    """Return whether adjacent caption/OCR language can satisfy Hybrid.

    Args:
        query: Original user text.

    Returns:
        True when ordinary Hybrid evidence may be used for a media query.
    """

    return _CAPTION_OCR.search(query) is not None


def comparison_wants_table(query: str, extract: DeterministicExtract) -> bool:
    """Return whether a comparison needs a StructuredTable branch.

    Args:
        query: Original user text.
        extract: Deterministic Phase 4 extract.

    Returns:
        True when numeric aggregation is requested.
    """

    lowered = query.lower()
    return extract.table_intent or (
        "sum" in lowered and ("sheet" in lowered or "column" in lowered)
    )


def comparison_wants_relationship(query: str, extract: DeterministicExtract) -> bool:
    """Return whether a comparison needs a Combined relationship branch.

    Args:
        query: Original user text.
        extract: Deterministic Phase 4 extract.

    Returns:
        True when impact/ownership chains are requested.
    """

    return extract.relationship_intent or _REL_HINT.search(query) is not None
