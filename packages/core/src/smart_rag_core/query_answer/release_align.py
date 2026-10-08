"""Split from ``release.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re

from smart_rag_core.query_answer.models import (
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.paragraphs import (
    drop_unsupported_paragraphs,
)
from smart_rag_core.query_answer.release_literals import (
    cited_source_text,
    fact_literals_missing,
    source_occurrence,
)
from smart_rag_core.query_answer.versions import PARAGRAPH_DELIMITER
from smart_rag_core.query_fusion.models import FusionResult

_QUOTED = re.compile(r"\"([^\"]{1,200})\"|'([^']{1,200})'|`([^`]{1,200})`")

_TRAILING_QUOTE_PUNCTUATION = ".,;:!?…"

_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")

_SNAKE_IDENTIFIER = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")


def _repair_split_identifier(
    link: AtomicLink,
    fusion: FusionResult,
) -> AtomicLink | None:
    """Restore snake_case tokens that the claim wrote with spaces.

    Args:
        link: Fact claim cited to one or more passages.
        fusion: Canonical passages.

    Returns:
        The link with source tokens restored, or ``None`` when no split
        token was repaired or the repaired claim still invents a literal
        or identifier.
    """

    if link.kind != "fact":
        return None
    source = cited_source_text(link, fusion=fusion, tables=())
    if not source:
        return None
    tokens = sorted(set(_SNAKE_IDENTIFIER.findall(source)), key=len, reverse=True)
    updated = link.claim
    replaced = False
    for token in tokens:
        if token in updated:
            continue
        spaced = token.replace("_", " ")
        pattern = re.compile(
            rf"(?<![\w]){re.escape(spaced)}(?![\w])(?!\s+[A-Za-z0-9])",
            re.IGNORECASE,
        )
        rewritten, count = pattern.subn(token, updated)
        if count:
            updated = rewritten
            replaced = True
    if not replaced or updated == link.claim:
        return None
    if fact_literals_missing(updated, source):
        return None
    source_tokens = set(_SNAKE_IDENTIFIER.findall(source))
    if not set(_SNAKE_IDENTIFIER.findall(updated)) <= source_tokens:
        return None
    return link.model_copy(update={"claim": updated})


def _verbatim_identifier_excerpt(source: str, claim: str) -> str | None:
    """Return a passage excerpt that already contains the claim's literals.

    Args:
        source: Cited canonical text.
        claim: Fact claim rejected by the verifier.

    Returns:
        A substring of ``source`` covering every quoted literal, number,
        and snake_case token in ``claim``, or ``None`` when any of those
        is absent or the excerpt would exceed 1000 characters.
    """

    if not source or fact_literals_missing(claim, source):
        return None
    claim_tokens = set(_SNAKE_IDENTIFIER.findall(claim))
    if not claim_tokens <= set(_SNAKE_IDENTIFIER.findall(source)):
        return None
    needles: list[str] = []
    for match in _QUOTED.finditer(claim):
        literal = next(item for item in match.groups() if item)
        found = source_occurrence(literal, source)
        if found is None:
            stripped = literal.rstrip(_TRAILING_QUOTE_PUNCTUATION)
            found = source_occurrence(stripped, source) if stripped else None
        if found:
            needles.append(found)
    needles.extend(token for token in claim_tokens if token in source)
    for match in _NUMBER.finditer(claim):
        if match.group(0) in source:
            needles.append(match.group(0))
    if not needles:
        return None
    host = source
    for part in source.split(PARAGRAPH_DELIMITER):
        if all(needle in part for needle in needles):
            host = part
            break
    start = min(host.find(needle) for needle in needles)
    end = max(host.find(needle) + len(needle) for needle in needles)
    left = host.rfind(". ", 0, start)
    right = host.find(". ", end)
    excerpt_start = 0 if left < 0 else left + 2
    excerpt_end = len(host) if right < 0 else right + 1
    excerpt = host[excerpt_start:excerpt_end].strip()
    if not excerpt or len(excerpt) > 1000 or PARAGRAPH_DELIMITER in excerpt:
        excerpt = host[start:end].strip()
    if (
        not excerpt
        or len(excerpt) > 1000
        or PARAGRAPH_DELIMITER in excerpt
        or excerpt not in source
    ):
        return None
    return excerpt


def align_split_source_identifiers(
    before: AnswerPayload,
    after: AnswerPayload,
    *,
    fusion: FusionResult,
) -> AnswerPayload:
    """Keep a fact the cited passage already states, and cite that passage.

    A verifier rejection is ignored only when every quoted literal, number,
    and snake_case token in the claim already occurs in the cited passage.
    The released claim and citation span then become one verbatim excerpt
    of that passage. No words are added. A name the passage does not
    contain stays dropped.

    Surviving claims that only split a source token, such as
    ``process numbers`` for ``process_numbers``, are rewritten to that
    token.

    Args:
        before: Answer the verifier received.
        after: Answer after unsupported links were removed.
        fusion: Canonical passages for the cited chunk IDs.

    Returns:
        ``after`` when nothing cited was restored. Otherwise the answer
        with grounded fact links kept and their text copied from the
        passage.
    """

    surviving = {link.link_id for link in after.atomic_links}
    repaired: dict[str, AtomicLink] = {}
    for link in before.atomic_links:
        if link.link_id in surviving:
            spacing = _repair_split_identifier(link, fusion)
            if spacing is not None:
                repaired[link.link_id] = spacing
            continue
        grounded = _ground_rejected_fact(link, before, fusion)
        if grounded is not None:
            repaired[link.link_id] = grounded
    if not repaired:
        return after
    merged_ids = surviving | set(repaired)
    links = tuple(
        repaired.get(link.link_id, link)
        for link in before.atomic_links
        if link.link_id in merged_ids
    )
    if links == after.atomic_links:
        return after
    paragraphs = tuple(
        paragraph.model_copy(
            update={
                "text": re.sub(
                    r"\n{2,}",
                    "\n",
                    restored.claim.replace("\r\n", "\n").replace("\r", "\n"),
                ).strip()[:4000]
            }
        )
        if (restored := repaired.get(paragraph.link_ids[0])) is not None
        and paragraph.link_ids == (restored.link_id,)
        else paragraph
        for paragraph in before.paragraphs
    )
    citations = tuple(
        citation.model_copy(update={"span": restored.claim})
        if (restored := repaired.get(citation.atomic_link_id or "")) is not None
        and citation.chunk_id in restored.chunk_ids
        and restored.claim in cited_source_text(restored, fusion=fusion, tables=())
        else citation
        for citation in before.citations
    )
    payload = before.model_copy(
        update={
            "atomic_links": links,
            "paragraphs": paragraphs,
            "citations": citations,
        }
    )
    unsupported = frozenset(
        link.link_id for link in before.atomic_links if link.link_id not in merged_ids
    )
    if not unsupported:
        return payload
    return drop_unsupported_paragraphs(payload, unsupported)


def _ground_rejected_fact(
    link: AtomicLink,
    payload: AnswerPayload,
    fusion: FusionResult,
) -> AtomicLink | None:
    """Return a rejected fact rewritten as a verbatim cited excerpt.

    Args:
        link: Fact claim the verifier removed.
        payload: Answer the verifier received, including citation spans.
        fusion: Canonical passages.

    Returns:
        The link whose claim is an excerpt of the cited passage, or
        ``None`` when the claim introduces a literal or identifier the
        passage does not contain.
    """

    del payload
    if link.kind != "fact":
        return None
    source = cited_source_text(link, fusion=fusion, tables=())
    excerpt = _verbatim_identifier_excerpt(source, link.claim)
    if excerpt is None:
        return None
    return link.model_copy(update={"claim": excerpt})
