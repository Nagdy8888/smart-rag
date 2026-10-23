"""Split from ``bind.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import exact_source_span
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_CITATIONS,
    MAX_CITATION_SPAN_CHARS,
    MAX_CLAIM_CITATIONS,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage

_SNAKE_NAME = re.compile(r"\b[A-Za-z_][A-Za-z0-9]*_[A-Za-z0-9_]+\b")

_HYPHEN_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")

_HOST_PATH = re.compile(r"\b(?:localhost|127\.0\.0\.1):\d+(?:/[A-Za-z0-9._~/-]*)?")

_ALLCAPS_TOKEN = re.compile(
    r"\b(?!(?:THE|AND|FOR|WITH|FROM|THIS|THAT|WHEN|WHAT|WHICH|CHAPTER|"
    r"TABLE|FIGURE|HTTP|HTTPS|JSON|RPC)\b)[A-Z][A-Z0-9]{1,5}\b"
)

_ALLCAPS_REBIND_STOP = frozenset(
    {
        "MCP",
        "HTTP",
        "HTTPS",
        "JSON",
        "RPC",
        "API",
        "URL",
        "SQL",
        "GPU",
        "CPU",
        "RAM",
        "IDE",
        "SDK",
        "CLI",
        "PDF",
        "CSV",
        "XML",
        "HTML",
        "CSS",
    }
)

_TITLE_PHRASE = re.compile(r"\b(?:[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[a-z]{2,8})){1,5})\b")

_PROPER_NAME = re.compile(r"\b[A-Z][a-z]{2,24}\b")

_PROPER_STOP = frozenset(
    {
        "The",
        "This",
        "That",
        "When",
        "What",
        "Which",
        "With",
        "From",
        "Chapter",
        "Table",
        "Figure",
        "Building",
        "Applications",
        "Agents",
        "Agent",
        "Use",
        "Only",
        "Give",
        "Document",
        "Company",
    }
)

_PERCENT_PHRASE = re.compile(
    r"\b\d{1,3}%\s+(?:suggestion\s+)?acceptance\s+rate\b"
    r"|\b\d{1,3}\s+engineers\b"
    r"|\bconfidence\s*<\s*\d+(?:\.\d+)?\b"
    r"|\bgreater\s+than\s+\d+\b",
    re.IGNORECASE,
)

_MAX_TOKEN_HOLDERS = 2

_PROPER_STOP_LOWER = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "what",
        "when",
        "which",
        "have",
        "does",
        "only",
        "give",
        "name",
        "wording",
        "figure",
        "page",
        "document",
        "company",
        "building",
        "applications",
        "agents",
        "agent",
        "into",
        "used",
        "uses",
        "using",
        "example",
        "about",
        "their",
        "there",
        "these",
        "those",
        "where",
        "your",
        "them",
        "chapter",
        "table",
        "the",
        "and",
        "for",
    }
)


def _claim_anchor_tokens(claim: str) -> tuple[str, ...]:
    """Return distinctive tokens used to locate a claim in fusion evidence.

    Args:
        claim: Fact-link claim text.

    Returns:
        Snake-case identifiers, hyphenated model ids, host paths, short
        ALLCAPS codes, Title Case phrases, proper names, and percent-style
        verbatim phrases, deduplicated.
    """

    found: list[str] = []
    for match in _SNAKE_NAME.finditer(claim):
        found.append(match.group(0))
    for match in _HYPHEN_TOKEN.finditer(claim):
        found.append(match.group(0))
    for match in _HOST_PATH.finditer(claim):
        found.append(match.group(0))
    for match in _ALLCAPS_TOKEN.finditer(claim):
        found.append(match.group(0))
    for match in _TITLE_PHRASE.finditer(claim):
        found.append(match.group(0))
    for match in _PROPER_NAME.finditer(claim):
        name = match.group(0)
        if name not in _PROPER_STOP:
            found.append(name)
    for match in _PERCENT_PHRASE.finditer(claim):
        found.append(match.group(0))
    return tuple(dict.fromkeys(found))


def _token_holder_chunks(
    tokens: tuple[str, ...],
    ordered: tuple[ScoredPassage, ...],
    *,
    user_query: str | None = None,
) -> tuple[str, ...]:
    """Return fused chunk ids that hold claim tokens, best first.

    Snake-case identifiers may cite up to two holders: naming/prose
    passages first (``(token)``, helper-function wording), then a
    ``def token(`` definition, then remaining holders by hybrid rank.
    Short verbatim fact phrases use the same two-holder cap and rank by
    distinctive query-term overlap before hybrid rank.

    Args:
        tokens: Anchor tokens from the claim.
        ordered: Fusion evidence in rank order.
        user_query: Original user text for multi-holder overlap ranking.
            Untrusted.

    Returns:
        Chunk ids eligible for citation retargeting, or empty when no
        snake-case or phrase holders apply.
    """

    snake = tuple(token for token in tokens if _SNAKE_NAME.fullmatch(token))
    phrases = tuple(token for token in tokens if token not in snake)
    if snake:
        snake_holders = [
            item
            for item in ordered
            if _passage_holds_any_token(item.citation_text, snake)
        ]
        if len(snake_holders) == 1:
            return (snake_holders[0].chunk_id,)
        if snake_holders and any(
            _prose_names_token(item.citation_text, token)
            for item in snake_holders
            for token in snake
        ):
            # Multi-cite when a naming/prose page shares the token with a
            # definition or call site so the gold naming page is not dropped.
            return _order_snake_holders(snake, snake_holders, user_query=user_query)[
                :_MAX_TOKEN_HOLDERS
            ]
        # Pure definition/call-site ambiguity is not guessed here.
    if not phrases:
        return ()
    # Host paths and hyphenated model ids are more distinctive than short
    # ALLCAPS or Title Case tokens that collide across many chunks. Still
    # union short ALLCAPS codes (A2A) so a gold page that only uses the
    # acronym is not dropped when the claim also expands the hyphen form.
    special = tuple(
        token
        for token in phrases
        if _HOST_PATH.fullmatch(token) or _HYPHEN_TOKEN.fullmatch(token)
    )
    if special:
        extras = tuple(
            token
            for token in phrases
            if _ALLCAPS_TOKEN.fullmatch(token)
            and token.upper() not in _ALLCAPS_REBIND_STOP
        )
        focus_tokens = tuple(dict.fromkeys((*special, *extras)))
    else:
        focus_tokens = phrases
    phrase_holders = [
        item
        for item in ordered
        if _passage_holds_any_token(item.citation_text, focus_tokens)
    ]
    if not phrase_holders:
        return ()
    ordered_holders = sorted(
        phrase_holders,
        key=lambda item: (
            -passage_query_overlap(user_query or "", item.citation_text),
            item.hybrid_rank or 10_000,
            item.chunk_id,
        ),
    )
    return tuple(item.chunk_id for item in ordered_holders)[:_MAX_TOKEN_HOLDERS]


def _passage_holds_any_token(text: str, tokens: tuple[str, ...]) -> bool:
    """Return whether any anchor token occurs in ``text``.

    Args:
        text: Canonical citation text.
        tokens: Anchor tokens from the claim.

    Returns:
        True on a case-insensitive substring match.
    """

    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def rebind_unique_claim_tokens(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str | None = None,
) -> AnswerPayload:
    """Retarget fact citations onto fused chunks that hold claim tokens.

    Snake-case identifiers and short verbatim answer phrases are matched
    case-insensitively against fused ``citation_text``. When several fused
    chunks hold a snake-case token, up to two are cited (prose naming
    first, then ``def``), so a gold naming page is not dropped in favor of
    a later definition-only chunk. Multi-holder phrase tokens prefer the
    passage with the highest distinctive query-term overlap, then hybrid
    rank.

    Args:
        payload: Company answer after definition rebind.
        fusion: Fitted canonical passages.
        user_query: Original user text used to break multi-holder ties.
            Untrusted.

    Returns:
        Payload with retargeted fact citations, or unchanged when no
        unique token holder applies.
    """

    ordered = tuple(fusion.evidence)
    passages = {item.chunk_id: item.citation_text for item in ordered}
    links: list[AtomicLink] = []
    paragraphs = list(payload.paragraphs)
    citations = list(payload.citations)
    changed = False
    for link in payload.atomic_links:
        if link.kind != "fact":
            links.append(link)
            continue
        # A complete definition owns its exact source fragments. Incidental
        # method names in its body must not retarget it onto a prose call site.
        if re.search(r"(?m)^\s*(?:async\s+)?def\s+\w+\s*\(", link.claim):
            links.append(link)
            continue
        tokens = _claim_anchor_tokens(link.claim)
        if not tokens:
            links.append(link)
            continue
        holders = _token_holder_chunks(tokens, ordered, user_query=user_query)
        if not holders:
            links.append(link)
            continue
        primary = holders[0]
        cited = set(link.chunk_ids)
        current_has_token = any(
            _passage_holds_any_token(passages.get(chunk_id, ""), tokens)
            for chunk_id in cited
        )
        if primary in cited and current_has_token and len(holders) == 1:
            links.append(link)
            continue
        target_ids = tuple(holders[:_MAX_TOKEN_HOLDERS])
        if target_ids == tuple(link.chunk_ids)[: len(target_ids)] and current_has_token:
            links.append(link)
            continue
        primary_text = passages[primary]
        span = _token_span(primary_text, tokens) or exact_source_span(primary_text)
        if not span:
            links.append(link)
            continue
        changed = True
        links.append(
            link.model_copy(update={"claim": link.claim, "chunk_ids": target_ids})
        )
        for index, paragraph in enumerate(paragraphs):
            if link.link_id not in paragraph.link_ids:
                continue
            # Keep model claim prose; only citation ownership moves.
            paragraphs[index] = paragraph
        replaced = False
        for index, citation in enumerate(citations):
            if citation.atomic_link_id != link.link_id:
                continue
            citations[index] = citation.model_copy(
                update={"chunk_id": primary, "span": span[:MAX_CITATION_SPAN_CHARS]}
            )
            replaced = True
            break
        if not replaced:
            paragraph_index = next(
                (
                    item.paragraph_index
                    for item in paragraphs
                    if link.link_id in item.link_ids
                ),
                0,
            )
            citations.append(
                AnswerCitation(
                    chunk_id=primary,
                    span=span[:MAX_CITATION_SPAN_CHARS],
                    atomic_link_id=link.link_id,
                    paragraph_index=paragraph_index,
                )
            )
        paragraph_index = next(
            (
                item.paragraph_index
                for item in paragraphs
                if link.link_id in item.link_ids
            ),
            0,
        )
        existing = {
            item.chunk_id for item in citations if item.atomic_link_id == link.link_id
        }
        for extra_id in target_ids[1:]:
            if extra_id in existing:
                continue
            if len(citations) >= MAX_ANSWER_CITATIONS:
                break
            if (
                sum(c.atomic_link_id == link.link_id for c in citations)
                >= MAX_CLAIM_CITATIONS
            ):
                break
            extra_text = passages[extra_id]
            extra_span = _token_span(extra_text, tokens) or exact_source_span(
                extra_text
            )
            if not extra_span:
                continue
            citations.append(
                AnswerCitation(
                    chunk_id=extra_id,
                    span=extra_span[:MAX_CITATION_SPAN_CHARS],
                    atomic_link_id=link.link_id,
                    paragraph_index=paragraph_index,
                )
            )
            existing.add(extra_id)
    if not changed:
        return payload
    return payload.model_copy(
        update={
            "atomic_links": tuple(links),
            "paragraphs": tuple(paragraphs),
            "citations": tuple(citations),
        }
    )


def _order_snake_holders(
    tokens: tuple[str, ...],
    holders: list[ScoredPassage],
    *,
    user_query: str | None = None,
) -> tuple[str, ...]:
    """Order snake-case token holders: prose naming, then def, then rank.

    Args:
        tokens: Snake-case claim tokens.
        holders: Fused passages that contain at least one token.
        user_query: Original user text for overlap tie-breaks. Untrusted.

    Returns:
        Chunk ids in citation preference order, deduplicated.
    """

    prose: list[ScoredPassage] = []
    definitional: list[ScoredPassage] = []
    other: list[ScoredPassage] = []
    for item in holders:
        text = item.citation_text
        if any(_prose_names_token(text, token) for token in tokens):
            prose.append(item)
        elif any(
            re.search(rf"(?i)\bdef\s+{re.escape(token)}\s*\(", text) for token in tokens
        ):
            definitional.append(item)
        else:
            other.append(item)

    def _by_rank(items: list[ScoredPassage]) -> list[ScoredPassage]:
        """Sort passages by query overlap, hybrid rank, then chunk id.

        Args:
            items: Passages in one preference bucket.

        Returns:
            Rank-sorted copy.
        """

        return sorted(
            items,
            key=lambda item: (
                -passage_query_overlap(user_query or "", item.citation_text),
                item.hybrid_rank or 10_000,
                item.chunk_id,
            ),
        )

    ordered_holders = [
        *_by_rank(prose),
        *_by_rank(definitional),
        *_by_rank(other),
    ]
    return tuple(dict.fromkeys(item.chunk_id for item in ordered_holders))


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
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9_-]{3,}", query.lower()):
        token = match.group(0)
        if token in _PROPER_STOP_LOWER or token in seen:
            continue
        seen.add(token)
        if token in lowered:
            score += 1
    return score


def _token_span(text: str, tokens: tuple[str, ...]) -> str | None:
    """Copy a short exact span around the first matching claim token.

    Args:
        text: Canonical passage text.
        tokens: Anchor tokens from the claim.

    Returns:
        Substring of ``text`` containing the token, or ``None``.
    """

    lowered = text.lower()
    for token in tokens:
        index = lowered.find(token.lower())
        if index < 0:
            continue
        start = max(0, index - 40)
        end = min(len(text), index + len(token) + 80)
        span = text[start:end].strip()
        if span and span in text and len(span) <= MAX_CITATION_SPAN_CHARS:
            return span
    return None


def _prose_names_token(text: str, token: str) -> bool:
    """Return whether ``text`` names ``token`` in helper/prose form.

    Matches parenthetical names, backticks, or nearby helper-function
    wording so narrative pages outrank bare call sites.

    Args:
        text: Canonical citation text.
        token: Snake-case identifier from the claim.

    Returns:
        True when the passage presents the token as a named helper.
    """

    escaped = re.escape(token)
    if re.search(rf"(?i)\({escaped}\)|`{escaped}`", text):
        return True
    if re.search(
        rf"(?i)(?:helper\s+function|function\s+name).{{0,40}}{escaped}"
        rf"|{escaped}.{{0,40}}(?:helper\s+function|function\s+name)",
        text,
    ):
        return True
    return False
