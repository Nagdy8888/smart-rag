"""Split from ``bind.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.versions import (
    MAX_CITATION_SPAN_CHARS,
)
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.text_constants import PARAGRAPH_DELIMITER

_MAX_DEFINITION_NAMES = 8

_CODE_ASK = re.compile(r"(?i)\b(?:snippets?|snippts?|snippt|source code)\b|\bcode\b")

_SNAKE_NAME = re.compile(r"\b[A-Za-z_][A-Za-z0-9]*_[A-Za-z0-9_]+\b")

_BACKTICK_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

_DECORATOR_TAIL = re.compile(r"(?:@[\w.]+\s+)+$")

_NEXT_FUNCTION = re.compile(r"(?:@[\w.]+\s+)*def\s+[A-Za-z_]\w*\s*\(")


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


def leaf_in_evidence(
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


def rebind_named_definitions(
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
