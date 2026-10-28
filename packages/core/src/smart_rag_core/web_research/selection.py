"""Deterministic public-source ranking and evidence-gap formulations."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from smart_rag_core.gateways.exa_search import ExaSearchCandidate
from smart_rag_core.web_research.heading_coverage import missing_level_references

_PUBLISHERS = {
    "python": "docs.python.org",
    "postgresql": "postgresql.org",
    "w3c": "w3.org",
    "wcag": "w3.org",
    "rfc": "rfc-editor.org",
}
_WORD = re.compile(r"[\w]+", re.UNICODE)
_STOP = frozenset(
    "according official documentation source cite explain compare what does with from using briefly include the and for its this that".split()
)


def rank_candidates(
    query: str, candidates: tuple[ExaSearchCandidate, ...]
) -> tuple[ExaSearchCandidate, ...]:
    """Prefer topical publisher/version matches without treating ranking as evidence."""
    lower = query.casefold()
    explicit = re.search(r"\b(python|postgresql)\s+(\d+(?:\.\d+)*)", lower)

    def score(candidate: ExaSearchCandidate) -> int:
        """Score topical relevance with publisher and version preferences."""
        host = (urlsplit(candidate.url).hostname or "").lower()
        haystack = f"{candidate.title} {candidate.url}".casefold()
        value = sum(
            2
            for term in set(_WORD.findall(lower))
            if len(term) > 2 and term in haystack
        )
        for keyword, domain in _PUBLISHERS.items():
            if keyword in lower and (host == domain or host.endswith("." + domain)):
                value += 30
        if "rfc" in lower and host == "httpwg.org":
            value += 30
        if explicit:
            version = explicit[2]
            if re.search(r"(?:/|\b)" + re.escape(version) + r"(?:/|\b)", haystack):
                value += 50
            elif re.search(r"/(?:docs/)?\d+(?:\.\d+)+/", candidate.url):
                value -= 100
        elif "python" in lower and host == "docs.python.org":
            value += 25 if "/3/" in candidate.url else -40
        elif "postgresql" in lower and "/current/" in candidate.url:
            value += 25
        return value

    eligible: list[ExaSearchCandidate] = []
    for candidate in candidates:
        path = urlsplit(candidate.url).path
        host = urlsplit(candidate.url).hostname or ""
        version = re.search(r"/(?:docs/)?(\d+(?:\.\d+)*)(?:/|$)", path)
        if explicit and version and ("python.org" in host or "postgresql.org" in host):
            if version[1] != explicit[2] and not version[1].startswith(
                explicit[2] + "."
            ):
                continue
        if (
            not explicit
            and "python" in lower
            and host == "docs.python.org"
            and version
            and version[1] != "3"
        ):
            continue
        eligible.append(candidate)
    return tuple(sorted(eligible, key=score, reverse=True))


def evidence_follow_ups(query: str, excerpts: tuple[str, ...]) -> tuple[str, ...]:
    """Search only missing explicit anchors/fields after reading first-round text.

    This is a conservative discovery heuristic. Semantic completeness is checked
    separately against the whole question before answer release.
    """
    joined = " ".join(excerpts).casefold()
    missing_levels = missing_level_references(query, excerpts)
    if missing_levels:
        return tuple(
            f"{query} {reference} conformance level"
            for reference in sorted(missing_levels)
        )[:2]
    if re.search(r"\bconformance\s+levels?\b", query, re.I) and re.search(
        r"\b\d+(?:\.\d+){2,}\b", query
    ):
        return ()
    anchors = set(
        re.findall(r"\b\d+(?:\.\d+){2,}\b|\b[A-Za-z]+[._][A-Za-z]+\b|\b\d{3}\b", query)
    )
    missing = [anchor for anchor in sorted(anchors) if anchor.casefold() not in joined]
    if missing:
        return tuple(f"{query} {anchor}" for anchor in missing[:2])
    terms = {
        term
        for term in _WORD.findall(query.casefold())
        if len(term) >= 4 and term not in _STOP
    }
    absent = sorted(term for term in terms if term not in joined)
    if not excerpts or (terms and len(absent) > len(terms) / 2):
        return (f"{query} {' '.join(absent[:4])}".strip(),)
    return ()
