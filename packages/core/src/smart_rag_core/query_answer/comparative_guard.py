"""Reject explicit opposite comparative directions in a named canonical topic."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import AtomicLink
from smart_rag_core.query_fusion.models import ScoredPassage

_METRIC = r"(?:latency|complexity|costs?|risks?|overhead|accuracy|speed)"
_DIRECTION = r"(?:higher|lower(?:s|ed|ing)?|greater|more|less|increas(?:e[sd]?|ing)|decreas(?:e[sd]?|ing)|reduc(?:e[sd]?|ing)|rais(?:e[sd]?|ing))"
_GROUP = rf"(?P<metrics>{_METRIC}(?:\s*(?:,|and|or)\s*{_METRIC})*)"
_PRE = re.compile(
    rf"\b(?P<direction>{_DIRECTION})\s+(?:overall\s+|total\s+|system\s+)?{_GROUP}\b",
    re.I,
)
_POST = re.compile(
    rf"\b{_GROUP}\s+(?:is|are|becomes?|remains?)\s+(?P<direction>{_DIRECTION})\b", re.I
)
_NEGATION = re.compile(r"\b(?:not|never|without|no|cannot)\b|n't\b", re.I)
_WORDS = re.compile(r"[a-z][a-z0-9_-]{2,}", re.I)
_GENERIC = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "overview",
        "introduction",
        "section",
        "chapter",
        "has",
        "have",
        "are",
        "may",
        "can",
        "that",
        "this",
        "which",
        "about",
        "using",
        "provides",
        "increases",
        "decreases",
        "higher",
        "lower",
        "more",
        "less",
        "greater",
        "reduces",
        "raises",
        "overall",
        "total",
    }
)


def explicit_comparative_conflict(
    link: AtomicLink, passages: dict[str, ScoredPassage]
) -> bool:
    """Compare only unambiguous metric directions within the cited named topic.

    Args:
        link: A factual claim with already authorized canonical source IDs.
        passages: Fitted canonical passages keyed by ID.

    Returns:
        True only for an explicit opposing direction. Mixed directions, negated
        phrases, unnamed scope, and inference links defer to the model verifier.
        This narrow check is not a general natural-language entailment engine.
    """
    if link.kind != "fact":
        return False
    claimed = _directions(link.claim)
    if not claimed:
        return False
    words = set(_WORDS.findall(link.claim.casefold()))
    sourced: dict[str, set[int]] = {}
    for chunk_id in link.chunk_ids:
        source = passages.get(chunk_id)
        if source is None:
            continue
        first = next((s for s in source.citation_text.splitlines() if s.strip()), "")
        first_heading = (
            first if len(first) <= 140 and not re.search(r"[.!?;:=]", first) else ""
        )
        heading = " ".join((*source.section_path, first_heading))
        topic = set(_WORDS.findall(heading.casefold())) - _GENERIC
        topic = {t for t in topic if not re.fullmatch(_METRIC, t)}
        if len(words & topic) < 2:
            continue
        for metric, values in _directions(source.citation_text).items():
            sourced.setdefault(metric, set()).update(values)
    return any(
        len(values) == 1
        and len(sourced.get(metric, set())) == 1
        and values != sourced[metric]
        for metric, values in claimed.items()
    )


def _directions(text: str) -> dict[str, set[int]]:
    """Extract adjacent comparative metric lists, excluding local negations."""
    found: dict[str, set[int]] = {}
    for pattern in (_PRE, _POST):
        for match in pattern.finditer(text):
            prefix = re.split(
                r"[.!?;\n]", text[max(0, match.start() - 45) : match.start()]
            )[-1]
            if _NEGATION.search(prefix):
                continue
            word = match.group("direction").casefold()
            sign = -1 if word.startswith(("lower", "less", "decreas", "reduc")) else 1
            for metric in re.findall(_METRIC, match.group("metrics"), re.I):
                found.setdefault(metric.casefold().rstrip("s"), set()).add(sign)
    return found
