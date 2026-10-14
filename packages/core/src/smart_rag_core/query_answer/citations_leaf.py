"""Split from ``citations.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload, AtomicLink
from smart_rag_core.query_answer.versions import MAX_CITATION_SPAN_CHARS
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage

_REASON_PREFIX = "query_citation:"

MIN_RETRY_SPAN_CHARS = 24

MIN_CLAIM_LOCAL_SPAN_CHARS = 12

_SENTENCE_END = re.compile(r"[.!?\u061f\u3002]\s|\n")

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


def drop_skipped_citations(
    answer: AnswerPayload,
    skipped: Sequence[SkippedCitation],
) -> AnswerPayload:
    """Remove passage citations that were not persisted.

    Args:
        answer: Verified answer payload.
        skipped: Citations skipped by ``persist_answer_citations``.

    Returns:
        Payload without the skipped citations. Paragraphs and atomic links
        are unchanged. Unchanged when nothing was skipped.
    """

    if not skipped:
        return answer
    keys = {(item.chunk_id, item.paragraph_index, item.span) for item in skipped}
    kept = tuple(
        citation
        for citation in answer.citations
        if (
            str(citation.chunk_id or ""),
            citation.paragraph_index,
            (citation.span or "").strip(),
        )
        not in keys
    )
    if len(kept) == len(answer.citations):
        return answer
    return answer.model_copy(update={"citations": kept})


@dataclass(frozen=True, slots=True)
class CitationPersistResult:
    """Outcome of one citation batch.

    Attributes:
        ids: Inserted ``app.citations`` ids in write order.
        skipped: Passage citations skipped for leaf-resolution reasons.
    """

    ids: tuple[UUID, ...] = ()
    skipped: tuple[SkippedCitation, ...] = ()


def _unique_claim_holder(
    link: AtomicLink,
    fusion: FusionResult,
) -> tuple[str, str] | None:
    """Return the unique fusion passage and claim-local span for one link.

    Args:
        link: Surviving atomic claim that still needs a leaf citation.
        fusion: Fitted canonical evidence.

    Returns:
        ``(chunk_id, span)`` when exactly one passage uniquely holds a
        claim-local excerpt. ``None`` when zero or several qualify.
    """

    claim = (link.claim or "").strip()
    if not claim:
        return None
    for span in _claim_span_candidates(claim):
        holders = [
            item
            for item in fusion.evidence
            if item.citation_text and span in item.citation_text
        ]
        if len(holders) != 1:
            continue
        holder = holders[0]
        return (str(holder.chunk_id), span)
    # Prefer the shortest passage that fully contains the claim when several
    # fused parents nest the same text — leaf persist needs one target.
    full_holders = [
        item
        for item in fusion.evidence
        if item.citation_text and claim in item.citation_text
    ]
    if not full_holders:
        return None
    full_holders.sort(key=lambda item: (len(item.citation_text), str(item.chunk_id)))
    shortest = full_holders[0]
    if len(full_holders) > 1 and len(full_holders[1].citation_text) == len(
        shortest.citation_text
    ):
        return None
    excerpt = claim[:MAX_CITATION_SPAN_CHARS].rstrip()
    if (
        len(excerpt) < MIN_CLAIM_LOCAL_SPAN_CHARS
        or excerpt not in shortest.citation_text
    ):
        return None
    return (str(shortest.chunk_id), excerpt)


def leading_sentence(span: str, *, minimum: int = MIN_RETRY_SPAN_CHARS) -> str:
    """Return the first sentence of a span when it is a strictly shorter retry.

    Args:
        span: Verbatim span already contained in the cited chunk text.
        minimum: Shortest acceptable retry length.

    Returns:
        Leading sentence including its terminal punctuation, or an empty
        string when the span has one sentence or the head is too short.
    """

    stripped = span.strip()
    match = _SENTENCE_END.search(stripped)
    if match is None:
        return ""
    head = stripped[: match.start() + 1].strip()
    if len(head) < minimum or head == stripped:
        return ""
    return head


def raise_citation_error(exc: BaseException) -> None:
    """Map a Postgres error to ``QueryAdmissionError``.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always.
    """

    raise QueryAdmissionError(citation_error_reason(exc)) from exc


@dataclass(frozen=True, slots=True)
class SkippedCitation:
    """One passage citation that could not be pinned to a single leaf.

    Attributes:
        chunk_id: Cited chunk id as text.
        paragraph_index: Paragraph the citation belonged to, if any.
        span: Span the model cited (already contained in the chunk text).
        reason: Last ``insert_run_citation_v2`` leaf-resolution reason.
    """

    chunk_id: str
    paragraph_index: int | None
    span: str
    reason: str


def repair_leaf_citations(
    answer: AnswerPayload,
    fusion: FusionResult,
    skipped: Sequence[SkippedCitation],
) -> AnswerPayload:
    """Rebuild skipped citations onto claim-local unique fusion spans.

    Parent passages and bare probes such as ``> 0.25`` or ``SHA-256`` often
    match several search-representative children and fail leaf persist. When
    the atomic claim (or a multi-token excerpt of it) sits inside exactly one
    fused passage, that passage and excerpt become the citation target so a
    second persist can succeed.

    Args:
        answer: Verified answer that still holds claim prose.
        fusion: Fitted canonical evidence for this run.
        skipped: Leaf-unresolved citations from the first persist attempt.

    Returns:
        Answer with repaired passage citations when a unique holder exists.
        Unchanged when nothing can be retargeted.
    """

    if not skipped or not fusion.evidence or not answer.atomic_links:
        return answer
    skip_keys = {
        (item.chunk_id, item.paragraph_index, (item.span or "").strip())
        for item in skipped
    }
    links_by_id = {item.link_id: item for item in answer.atomic_links}
    links_by_paragraph: dict[int, AtomicLink] = {}
    for paragraph in answer.paragraphs:
        for link_id in paragraph.link_ids:
            link = links_by_id.get(link_id)
            if link is not None:
                links_by_paragraph[paragraph.paragraph_index] = link
                break
    repaired: list[AnswerCitation] = []
    link_updates: dict[str, str] = {}
    changed = False
    for citation in answer.citations:
        key = (
            str(citation.chunk_id or ""),
            citation.paragraph_index,
            (citation.span or "").strip(),
        )
        if key not in skip_keys:
            repaired.append(citation)
            continue
        link = None
        if citation.atomic_link_id:
            link = links_by_id.get(citation.atomic_link_id)
        if link is None and citation.paragraph_index is not None:
            link = links_by_paragraph.get(citation.paragraph_index)
        target = _unique_claim_holder(link, fusion) if link is not None else None
        if target is None:
            repaired.append(citation)
            continue
        chunk_id, span = target
        repaired.append(
            citation.model_copy(
                update={
                    "chunk_id": chunk_id,
                    "span": span[:MAX_CITATION_SPAN_CHARS],
                }
            )
        )
        if link is not None and chunk_id not in link.chunk_ids:
            link_updates[link.link_id] = chunk_id
        changed = True
    if not changed:
        return answer
    links = answer.atomic_links
    if link_updates:
        links = tuple(
            item.model_copy(
                update={"chunk_ids": (link_updates[item.link_id], *item.chunk_ids)}
            )
            if item.link_id in link_updates
            else item
            for item in answer.atomic_links
        )
    return answer.model_copy(
        update={"citations": tuple(repaired), "atomic_links": links}
    )


def shorten_contained_skipped_spans(
    answer: AnswerPayload,
    fusion: FusionResult,
    skipped: Sequence[SkippedCitation],
) -> AnswerPayload:
    """Keep a paragraph whose skipped span is an exact fused-passage slice.

    The citation span becomes the leading sentence when that sentence is
    still inside the same passage. Paragraph text and ``answer_text`` stay
    so a later citation drop cannot remove the fact. The caller retries
    persistence with the shorter span.

    Args:
        answer: Verified answer that still holds the paragraph.
        fusion: Fitted canonical evidence for this run.
        skipped: Leaf-unresolved citations from the first persist attempt.

    Returns:
        Answer with shortened citation spans when a contained opening can
        be retried. Unchanged when no skipped span sits in a fused passage.
    """

    if not skipped or not fusion.evidence or not answer.citations:
        return answer
    passages = tuple(
        item.citation_text for item in fusion.evidence if item.citation_text
    )
    if not passages:
        return answer
    skip_keys = {
        (item.chunk_id, item.paragraph_index, (item.span or "").strip())
        for item in skipped
    }
    rewritten: list[AnswerCitation] = []
    changed = False
    for citation in answer.citations:
        span = (citation.span or "").strip()
        key = (str(citation.chunk_id or ""), citation.paragraph_index, span)
        if key not in skip_keys:
            rewritten.append(citation)
            continue
        holder = next((text for text in passages if span in text), None)
        sentence = leading_sentence(span) if holder is not None else ""
        if holder is None or not sentence or sentence not in holder:
            rewritten.append(citation)
            continue
        rewritten.append(citation.model_copy(update={"span": sentence}))
        changed = True
    if not changed:
        return answer
    return answer.model_copy(update={"citations": tuple(rewritten)})


def citation_error_reason(exc: BaseException) -> str:
    """Extract the ``query_citation:`` reason from a database error.

    Args:
        exc: Driver or database error.

    Returns:
        Reason token, or ``database_rejected`` when the message has none.
    """

    message = str(exc)
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        return tail.split("\n")[0]
    return "database_rejected"


def _passage_locator_fields(scored: ScoredPassage | None) -> dict[str, object]:
    """Copy page/section/sheet/URL locators from fusion evidence.

    Args:
        scored: Matching fusion passage, or ``None``.

    Returns:
        Locator mapping without empty values or passage text.
    """

    if scored is None:
        return {}
    payload: dict[str, object] = {
        "document_id": scored.document_id,
        "version_id": scored.version_id,
        "page_number": scored.page_number,
        "section_path": list(scored.section_path),
        "sheet_name": scored.sheet_name,
        "range_ref": scored.range_ref,
        "source_url": scored.source_url,
    }
    return {
        key: value for key, value in payload.items() if value not in (None, "", (), [])
    }


def citation_provenance_payload(
    *,
    fusion: FusionResult,
    answer: AnswerPayload,
    chunk_id: str | None,
    table_id: str | None,
    atomic_link_id: str | None,
    inference: bool,
    source_ranges: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build expand-only provenance for one ``app.citations`` row.

    Fusion scores, algorithm, and config hash live in jsonb so packet 3
    does not require a new table. Locator coordinates are stored without
    passage text.

    Args:
        fusion: Combined ranking result.
        answer: Verified answer.
        chunk_id: Canonical chunk when present.
        table_id: Canonical table when present.
        atomic_link_id: Owning atomic link.
        inference: True when the citation supports a composed inference.
        source_ranges: Exact table ranges when this is a table citation.

    Returns:
        JSON-serializable provenance mapping.
    """

    scored = next(
        (item for item in fusion.evidence if item.chunk_id == chunk_id),
        None,
    )
    payload: dict[str, object] = {
        "algorithm": fusion.algorithm.value,
        "config_hash": fusion.config_hash,
        "requested_route": fusion.requested_route,
        "effective_route": fusion.effective_route,
        "fallback_reason": fusion.fallback_reason,
        "chunk_id": chunk_id,
        "table_id": table_id,
        "hybrid_rank": scored.hybrid_rank if scored is not None else None,
        "graph_rank": scored.graph_rank if scored is not None else None,
        "combined_score": scored.combined_score if scored is not None else None,
        "graph_discovered_only": (
            scored.graph_discovered_only if scored is not None else False
        ),
        "path_support": scored.path_support if scored is not None else None,
        "atomic_link_id": atomic_link_id,
        "inference": inference,
        "answer_status": answer.status,
        "keyword_extract_count": 0,
        "lightrag_answer_generate_count": 0,
        **_passage_locator_fields(scored),
    }
    if source_ranges:
        payload["source_ranges"] = list(source_ranges)
    return payload


def _claim_span_candidates(claim: str) -> tuple[str, ...]:
    """Build longest-first claim excerpts suitable as unique leaf spans.

    Args:
        claim: Atomic claim text released into the answer.

    Returns:
        Distinct substrings of ``claim``, longest first, excluding bare
        probes shorter than ``MIN_CLAIM_LOCAL_SPAN_CHARS``.
    """

    stripped = claim.strip()
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        """Record one candidate when it is long enough and new.

        Args:
            value: Candidate substring.
        """

        text = value.strip()
        if len(text) > MAX_CITATION_SPAN_CHARS:
            text = text[:MAX_CITATION_SPAN_CHARS].rstrip()
        if len(text) < MIN_CLAIM_LOCAL_SPAN_CHARS or text in seen:
            return
        seen.add(text)
        ordered.append(text)

    _add(stripped)
    for match in _SENTENCE_END.finditer(stripped):
        _add(stripped[: match.start() + 1])
    tokens = [item.group(0) for item in _TOKEN.finditer(stripped)]
    if len(tokens) >= 2:
        for width in range(min(len(tokens), 8), 1, -1):
            for start in range(0, len(tokens) - width + 1):
                left = stripped.lower().find(tokens[start].lower())
                right_token = tokens[start + width - 1]
                right = stripped.lower().find(
                    right_token.lower(), left if left >= 0 else 0
                )
                if left >= 0 and right >= left:
                    _add(stripped[left : right + len(right_token)])
    ordered.sort(key=len, reverse=True)
    return tuple(ordered)
