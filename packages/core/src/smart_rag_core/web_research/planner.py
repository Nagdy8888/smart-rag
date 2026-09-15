"""Bound search formulations for Web research."""

from __future__ import annotations

from smart_rag_core.gateways.exa_search import EXA_MAX_QUERY_CHARS
from smart_rag_core.web_research.bounds import WEB_MAX_FORMULATIONS


def propose_follow_ups(query: str, titles: tuple[str, ...]) -> tuple[str, ...]:
    """Return at most two title-derived follow-ups. Never a third round.

    This deterministic critique implements ``web_critique_v1``: empty when
    titles already echo the query, otherwise one or two public-web strings
    that still must pass ``sanitize_exa_query`` before Exa.

    Args:
        query: Sanitized first-round query.
        titles: First-round result titles only. Never URLs or excerpts.

    Returns:
        Zero to two follow-up strings, unique ignoring case.
    """

    extras: list[str] = []
    seen = {query.casefold()}
    for title in titles:
        cleaned = title.strip()
        if not cleaned:
            continue
        if cleaned.casefold() in query.casefold() or cleaned.casefold() in seen:
            continue
        candidate = f"{query} {cleaned}"[:EXA_MAX_QUERY_CHARS].strip()
        key = candidate.casefold()
        if not candidate or key in seen:
            continue
        seen.add(key)
        extras.append(candidate)
        if len(extras) >= 2:
            break
    return tuple(extras)


def bound_formulations(
    initial: str,
    follow_ups: tuple[str, ...],
) -> tuple[str, ...]:
    """Keep the initial query plus at most two follow-ups.

    Args:
        initial: Sanitized first-round query.
        follow_ups: Critique-proposed follow-ups, already sanitized.

    Returns:
        Unique non-empty formulations, length 1-3. The first item is
        always ``initial``. A fourth string is dropped, not searched.
    """

    ordered: list[str] = [initial]
    seen = {initial.casefold()}
    for item in follow_ups:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
        if len(ordered) >= WEB_MAX_FORMULATIONS:
            break
    return tuple(ordered)
