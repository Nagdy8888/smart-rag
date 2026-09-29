"""Bind omitted company paragraphs, links, and exact citation spans."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import exact_source_span
from smart_rag_core.query_answer.versions import (
    MAX_ANSWER_CITATIONS,
    MAX_ANSWER_PARAGRAPHS,
    MAX_CITATION_SPAN_CHARS,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.text_constants import PARAGRAPH_DELIMITER

_MAX_DEFINITION_NAMES = 8
_CODE_ASK = re.compile(r"(?i)\b(?:snippets?|snippts?|snippt|source code)\b|\bcode\b")
_SNAKE_NAME = re.compile(r"\b[A-Za-z_][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
_HYPHEN_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")
_HOST_PATH = re.compile(
    r"\b(?:localhost|127\.0\.0\.1):\d+(?:/[A-Za-z0-9._~/-]*)?"
)
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
_TITLE_PHRASE = re.compile(
    r"\b(?:[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|[a-z]{2,8})){1,5})\b"
)
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
_BACKTICK_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
_DECORATOR_TAIL = re.compile(r"(?:@[\w.]+\s+)+$")
_NEXT_FUNCTION = re.compile(r"(?:@[\w.]+\s+)*def\s+[A-Za-z_]\w*\s*\(")


def bind_company_atomic_links(
    payload: AnswerPayload,
    *,
    fusion: FusionResult | None = None,
    user_query: str | None = None,
) -> AnswerPayload:
    """Fill omitted atomic links, citation ids, and exact source spans.

    Four evidence-preserving repairs run before the paragraph contract:

    - A parent citation whose span sits inside exactly one nested evidence
      chunk is retargeted to that leaf.
    - A citation whose ``atomic_link_id`` is missing or not one of its
      paragraph's link ids takes the paragraph's first link id.
    - A fact claim that names one function defined in exactly one other
      fused chunk is moved onto that chunk. The claim and span become
      the exact definition text, including a leading decorator.
    - A fact claim whose distinctive snake-case token or short verbatim
      phrase sits in fused evidence is retargeted onto up to two holding
      chunks (prose naming first for identifiers) when the current
      citation misses the preferred holder.
    - Each atomic link's ``chunk_ids`` gains the chunks its citations
      already cite, capped at 12.

    None of these repairs can add a chunk id that is not already in the
    fused evidence the paragraph contract will check verbatim.

    Args:
        payload: Company answer after invented-ID filtering.
        fusion: Fitted canonical evidence used to copy exact spans.
            Omitted when the caller only needs link synthesis.
        user_query: Original user text. Used only to notice a code
            request when the answer has a single fact claim. Untrusted.

    Returns:
        Payload with synthesized fact links, citation ``atomic_link_id``
        values, contained spans, and repaired link chunk lists.
        Unchanged when paragraphs are ungrounded.
    """

    working = payload
    if not working.paragraphs and working.atomic_links:
        working = _paragraphs_from_links(working, fusion)
    paragraphs = tuple(_paragraph_with_link_id(item) for item in working.paragraphs)
    citations = tuple(
        _citation_with_link_id(citation, paragraphs) for citation in working.citations
    )
    table_citations = tuple(
        _citation_with_link_id(citation, paragraphs)
        for citation in working.table_citations
    )
    working = working.model_copy(
        update={
            "paragraphs": paragraphs,
            "citations": citations,
            "table_citations": table_citations,
        }
    )
    if not working.atomic_links:
        synthesized = _links_from_paragraphs(working)
        if synthesized:
            working = working.model_copy(update={"atomic_links": synthesized})
    if fusion is None:
        return _repair_link_chunk_ids(working)
    aligned = _align_citation_spans(working, fusion)
    rebound = _rebind_named_definitions(aligned, fusion, user_query=user_query)
    token_bound = _rebind_unique_claim_tokens(
        rebound, fusion, user_query=user_query
    )
    return _repair_link_chunk_ids(token_bound)


def _paragraphs_from_links(
    payload: AnswerPayload,
    fusion: FusionResult | None,
) -> AnswerPayload:
    """Build paragraphs and exact-span citations from omitted paragraph lists.

    Live ``answer_v3`` payloads sometimes emit atomic links without
    paragraphs. Deterministic paragraph mapping then fail-closes before
    the verifier. Claims stay owned by the links; spans are copied from
    authorized ``citation_text`` when fusion is available.

    Args:
        payload: Company answer with atomic links and empty paragraphs.
        fusion: Fitted canonical passages, or ``None`` when spans cannot
            be copied yet.

    Returns:
        Payload with one paragraph per link and contained citation spans
        for authorized chunk IDs. Unchanged when no grounded citation
        can be built.
    """

    passages = (
        {item.chunk_id: item for item in fusion.evidence} if fusion is not None else {}
    )
    paragraphs: list[AnswerParagraph] = []
    citations: list[AnswerCitation] = []
    for index, link in enumerate(payload.atomic_links[:MAX_ANSWER_PARAGRAPHS]):
        claim = link.claim.strip()
        if not claim:
            continue
        paragraphs.append(
            AnswerParagraph(
                paragraph_index=index,
                text=claim[:4000],
                link_ids=(link.link_id,),
            )
        )
        for chunk_id in link.chunk_ids:
            if len(citations) >= MAX_ANSWER_CITATIONS:
                break
            passage = passages.get(chunk_id)
            span = (
                exact_source_span(passage.citation_text) if passage is not None else ""
            )
            if passage is None or not span:
                continue
            citations.append(
                AnswerCitation(
                    chunk_id=chunk_id,
                    span=span,
                    paragraph_index=index,
                    atomic_link_id=link.link_id,
                )
            )
    if not paragraphs:
        return payload
    updates: dict[str, object] = {"paragraphs": tuple(paragraphs)}
    if citations and not payload.citations:
        updates["citations"] = tuple(citations)
    return payload.model_copy(update=updates)


def _paragraph_with_link_id(paragraph: AnswerParagraph) -> AnswerParagraph:
    """Copy a paragraph, filling a synthetic link id when omitted.

    Args:
        paragraph: Company paragraph from the model payload.

    Returns:
        The paragraph, or a copy with ``p{index}`` as its only link id.
    """

    if paragraph.link_ids:
        return paragraph
    return paragraph.model_copy(update={"link_ids": (f"p{paragraph.paragraph_index}",)})


def _align_citation_spans(
    payload: AnswerPayload,
    fusion: FusionResult,
) -> AnswerPayload:
    """Replace missing or non-substring spans with exact source excerpts.

    Args:
        payload: Company answer after link binding.
        fusion: Fitted canonical passages.

    Returns:
        Payload whose passage citation spans are empty-or-contained
        substrings of authorized ``citation_text``. Unauthorized chunk
        IDs are left unchanged for later fail-closed checks.
    """

    passages = {item.chunk_id: item for item in fusion.evidence}
    aligned: list[AnswerCitation] = []
    for citation in payload.citations:
        chunk_id = citation.chunk_id
        if chunk_id is None or chunk_id not in passages:
            aligned.append(citation)
            continue
        text = passages[chunk_id].citation_text
        span = citation.span
        if not (span and span in text):
            replacement = exact_source_span(text)
            if not replacement:
                aligned.append(citation)
                continue
            span = replacement
        leaf = _leaf_in_evidence(chunk_id, span, passages)
        update: dict[str, object] = {"span": span}
        if leaf is not None:
            update["chunk_id"] = leaf
        aligned.append(citation.model_copy(update=update))
    return payload.model_copy(update={"citations": tuple(aligned)})


def _rebind_named_definitions(
    payload: AnswerPayload,
    fusion: FusionResult,
    *,
    user_query: str | None,
) -> AnswerPayload:
    """Move a mis-cited function claim onto the chunk that defines it.

    A paraphrase cited to a neighboring page otherwise survives span
    repair and is then refused, which drops the only paragraph. The
    repair runs only when exactly one fused chunk contains ``def name(``
    and the claim does not already cite that chunk. Two defining chunks,
    or two eligible names, stay unchanged.

    Args:
        payload: Company answer after span alignment.
        fusion: Fitted canonical passages.
        user_query: Original user text. Names in the query are considered
            only for a code request with a single fact claim.

    Returns:
        Payload whose eligible fact claim, paragraph, and citation quote
        the exact definition. Unchanged when no unique definition applies.
    """

    passages = {item.chunk_id: item.citation_text for item in fusion.evidence}
    query_names: tuple[str, ...] = ()
    fact_count = sum(1 for link in payload.atomic_links if link.kind == "fact")
    if fact_count == 1 and _asks_for_code(user_query):
        query_names = _definition_names(user_query or "")
    links: list[AtomicLink] = []
    paragraphs = list(payload.paragraphs)
    citations = list(payload.citations)
    changed = False
    for link in payload.atomic_links:
        if link.kind != "fact":
            links.append(link)
            continue
        names = _definition_names(link.claim)
        if query_names:
            names = tuple(dict.fromkeys((*names, *query_names)))[:_MAX_DEFINITION_NAMES]
        rebound = _unique_definition(names, passages, cited=set(link.chunk_ids))
        if rebound is None:
            links.append(link)
            continue
        chunk_id, span = rebound
        changed = True
        links.append(link.model_copy(update={"claim": span, "chunk_ids": (chunk_id,)}))
        for index, paragraph in enumerate(paragraphs):
            if paragraph.link_ids != (link.link_id,):
                continue
            paragraphs[index] = paragraph.model_copy(update={"text": span})
        replaced = False
        for index, citation in enumerate(citations):
            if citation.atomic_link_id != link.link_id:
                continue
            citations[index] = citation.model_copy(
                update={"chunk_id": chunk_id, "span": span}
            )
            replaced = True
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
                    chunk_id=chunk_id,
                    span=span,
                    atomic_link_id=link.link_id,
                    paragraph_index=paragraph_index,
                )
            )
    if not changed:
        return payload
    return payload.model_copy(
        update={
            "atomic_links": tuple(links),
            "paragraphs": tuple(paragraphs),
            "citations": tuple(citations),
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


def _rebind_unique_claim_tokens(
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
        tokens = _claim_anchor_tokens(link.claim)
        if not tokens:
            links.append(link)
            continue
        holders = _token_holder_chunks(
            tokens, ordered, user_query=user_query
        )
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
            item.chunk_id
            for item in citations
            if item.atomic_link_id == link.link_id
        }
        for extra_id in target_ids[1:]:
            if extra_id in existing:
                continue
            if len(citations) >= MAX_ANSWER_CITATIONS:
                break
            extra_text = passages[extra_id]
            extra_span = (
                _token_span(extra_text, tokens) or exact_source_span(extra_text)
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
            return _order_snake_holders(
                snake, snake_holders, user_query=user_query
            )[:_MAX_TOKEN_HOLDERS]
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
            -_passage_query_overlap(user_query or "", item.citation_text),
            item.hybrid_rank or 10_000,
            item.chunk_id,
        ),
    )
    return tuple(item.chunk_id for item in ordered_holders)[:_MAX_TOKEN_HOLDERS]


def _passage_query_overlap(query: str, text: str) -> int:
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
            re.search(rf"(?i)\bdef\s+{re.escape(token)}\s*\(", text)
            for token in tokens
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
                -_passage_query_overlap(user_query or "", item.citation_text),
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


def _asks_for_code(user_query: str | None) -> bool:
    """Return whether the user asked for a source snippet.

    Args:
        user_query: Original user text. Untrusted. ``None`` when the
            caller did not supply it.

    Returns:
        True for snippet, snippt, source code, or the word code.
    """

    if not user_query:
        return False
    return _CODE_ASK.search(user_query) is not None


def _definition_names(text: str) -> tuple[str, ...]:
    """Return bounded function-shaped identifiers from untrusted text.

    Args:
        text: Claim or user query.

    Returns:
        Snake-case and backtick identifiers, at most eight, in order.
    """

    found: list[str] = []
    for match in _BACKTICK_NAME.finditer(text):
        found.append(match.group(1))
    found.extend(match.group(0) for match in _SNAKE_NAME.finditer(text))
    return tuple(dict.fromkeys(found))[:_MAX_DEFINITION_NAMES]


def _unique_definition(
    names: tuple[str, ...],
    passages: dict[str, str],
    *,
    cited: set[str],
) -> tuple[str, str] | None:
    """Return the one uncited function defined by exactly one passage.

    Args:
        names: Candidate identifiers from the claim or query.
        passages: Fusion citation text by chunk id.
        cited: Chunk ids already attached to the claim.

    Returns:
        ``(chunk_id, span)`` when exactly one name qualifies. ``None``
        when zero or several definitions would have to be chosen.
    """

    matches: list[tuple[str, str]] = []
    for name in names:
        holders: list[tuple[str, str]] = []
        for chunk_id, text in passages.items():
            span = _function_span(text, name)
            if span is not None:
                holders.append((chunk_id, span))
        if len(holders) != 1:
            continue
        chunk_id, span = holders[0]
        if chunk_id in cited:
            continue
        matches.append((chunk_id, span))
    if len(matches) != 1:
        return None
    return matches[0]


def _function_span(text: str, name: str) -> str | None:
    """Copy one exact function definition, including a leading decorator.

    The copy stops at the next function or a blank line so the paragraph
    delimiter cannot enter the claim. It stays a substring of ``text``
    and within the citation span cap.

    Args:
        text: Canonical passage text.
        name: Function identifier to locate.

    Returns:
        Exact definition substring, or ``None`` when ``text`` does not
        define ``name``.
    """

    match = re.search(rf"def\s+{re.escape(name)}\s*\(", text)
    if match is None:
        return None
    paragraph_start = text.rfind(PARAGRAPH_DELIMITER, 0, match.start())
    paragraph_start = (
        0 if paragraph_start < 0 else paragraph_start + len(PARAGRAPH_DELIMITER)
    )
    prefix = text[paragraph_start : match.start()]
    decorator = _DECORATOR_TAIL.search(prefix)
    start = paragraph_start + decorator.start() if decorator else match.start()
    window = text[match.end() : start + MAX_CITATION_SPAN_CHARS]
    cuts = [len(window)]
    blank = window.find(PARAGRAPH_DELIMITER)
    if blank >= 0:
        cuts.append(blank)
    nxt = _NEXT_FUNCTION.search(window)
    if nxt is not None:
        cuts.append(nxt.start())
    span = text[start : match.end() + min(cuts)].strip()
    if len(span) > MAX_CITATION_SPAN_CHARS:
        span = span[:MAX_CITATION_SPAN_CHARS].rstrip()
    if (
        not span
        or PARAGRAPH_DELIMITER in span
        or span not in text
        or re.search(rf"def\s+{re.escape(name)}\s*\(", span) is None
    ):
        return None
    return span


def _leaf_in_evidence(
    chunk_id: str,
    span: str,
    passages: dict[str, ScoredPassage],
) -> str | None:
    """Return the one evidence chunk nested in ``chunk_id`` that holds ``span``.

    Parent passages concatenate their children. When the model cites the
    parent and the span sits inside exactly one child that is also in
    evidence, the child is the page-precise citation target and the
    database leaf rule will accept it.

    Args:
        chunk_id: Cited chunk id.
        span: Verbatim span contained in the cited chunk's text.
        passages: Fusion evidence by chunk id.

    Returns:
        Child chunk id, or None when zero or several children qualify.
    """

    parent_text = passages[chunk_id].citation_text
    if not span or not parent_text:
        return None
    leaves = [
        other_id
        for other_id, other in passages.items()
        if other_id != chunk_id
        and other.citation_text
        and len(other.citation_text) < len(parent_text)
        and other.citation_text in parent_text
        and span in other.citation_text
    ]
    if len(leaves) != 1:
        return None
    return leaves[0]


def _citation_with_link_id(
    citation: AnswerCitation,
    paragraphs: tuple[AnswerParagraph, ...],
) -> AnswerCitation:
    """Copy a citation, filling ``atomic_link_id`` from its paragraph.

    Args:
        citation: Passage or table citation.
        paragraphs: Ordered company paragraphs.

    Returns:
        The citation, or a copy whose ``atomic_link_id`` is the
        paragraph's first link id when it was missing or not one of the
        paragraph's links.
    """

    paragraph = next(
        (
            item
            for item in paragraphs
            if item.paragraph_index == citation.paragraph_index
        ),
        None,
    )
    if paragraph is None or not paragraph.link_ids:
        return citation
    if citation.atomic_link_id and citation.atomic_link_id in paragraph.link_ids:
        return citation
    return citation.model_copy(update={"atomic_link_id": paragraph.link_ids[0]})


def _links_from_paragraphs(payload: AnswerPayload) -> tuple[AtomicLink, ...]:
    """Build fact links from grounded paragraphs when the model omitted them.

    Args:
        payload: Company answer with paragraphs and citations.

    Returns:
        One fact link per paragraph that cites at least one passage or
        table. Empty when paragraphs cannot be grounded.
    """

    synthesized: list[AtomicLink] = []
    for paragraph in payload.paragraphs:
        chunk_ids: list[str] = []
        for citation in payload.citations:
            chunk_id = citation.chunk_id
            if (
                citation.paragraph_index != paragraph.paragraph_index
                or not chunk_id
                or chunk_id in chunk_ids
            ):
                continue
            chunk_ids.append(chunk_id)
        table_citation = next(
            (
                citation
                for citation in payload.table_citations
                if citation.paragraph_index == paragraph.paragraph_index
                and citation.table_id
            ),
            None,
        )
        if not chunk_ids and table_citation is None:
            continue
        link_id = (
            paragraph.link_ids[0]
            if paragraph.link_ids
            else f"p{paragraph.paragraph_index}"
        )
        synthesized.append(
            AtomicLink(
                link_id=link_id[:64],
                claim=paragraph.text[:2000],
                chunk_ids=tuple(chunk_ids[:12]),
                table_id=None if table_citation is None else table_citation.table_id,
                source_ranges=(
                    () if table_citation is None else table_citation.source_ranges
                ),
                kind="fact",
                priority=paragraph.paragraph_index + 1,
            )
        )
    return tuple(synthesized)


def _repair_link_chunk_ids(payload: AnswerPayload) -> AnswerPayload:
    """Extend each link's ``chunk_ids`` with the chunks its citations cite.

    The paragraph contract rejects a citation whose chunk is not listed on
    its link. Citations are the stronger signal because their spans are
    checked verbatim against authorized passages; links are bookkeeping.
    The cap of 12 matches the link synthesis slice in this module.

    Args:
        payload: Company answer after link-id binding and span alignment.

    Returns:
        Payload whose links list every cited chunk, capped at 12 per link.
        Unchanged when nothing was missing.
    """

    cited: dict[str, list[str]] = {}
    for citation in payload.citations:
        if not citation.atomic_link_id or not citation.chunk_id:
            continue
        bucket = cited.setdefault(citation.atomic_link_id, [])
        if citation.chunk_id not in bucket:
            bucket.append(citation.chunk_id)
    changed = False
    links: list[AtomicLink] = []
    for link in payload.atomic_links:
        missing = [
            chunk_id
            for chunk_id in cited.get(link.link_id, [])
            if chunk_id not in link.chunk_ids
        ]
        if not missing:
            links.append(link)
            continue
        changed = True
        merged = (*link.chunk_ids, *missing)[:12]
        links.append(link.model_copy(update={"chunk_ids": merged}))
    if not changed:
        return payload
    return payload.model_copy(update={"atomic_links": tuple(links)})
