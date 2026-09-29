"""Citation provenance payloads for existing ``app.citations.provenance`` jsonb."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import list_run_citations
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload, AtomicLink
from smart_rag_core.query_answer.versions import MAX_CITATION_SPAN_CHARS
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.web_research.models import WebSourceRecord

LOGGER = logging.getLogger(__name__)

_REASON_PREFIX = "query_citation:"

LEAF_RESOLUTION_REASONS = frozenset(
    {"span_not_contained", "leaf_ambiguous", "page_ambiguous"}
)
"""``insert_run_citation_v2`` reasons that describe one citation's leaf
resolution rather than the run, the caller, or the transaction."""

MIN_RETRY_SPAN_CHARS = 24
"""Shortest leading sentence worth retrying as a narrower span."""

MIN_CLAIM_LOCAL_SPAN_CHARS = 12
"""Shortest claim excerpt worth using as a unique leaf span."""

_SENTENCE_END = re.compile(r"[.!?\u061f\u3002]\s|\n")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


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


@dataclass(frozen=True, slots=True)
class CitationPersistResult:
    """Outcome of one citation batch.

    Attributes:
        ids: Inserted ``app.citations`` ids in write order.
        skipped: Passage citations skipped for leaf-resolution reasons.
    """

    ids: tuple[UUID, ...] = ()
    skipped: tuple[SkippedCitation, ...] = ()


def _citation_error_reason(exc: BaseException) -> str:
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


def _raise_citation_error(exc: BaseException) -> None:
    """Map a Postgres error to ``QueryAdmissionError``.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always.
    """

    raise QueryAdmissionError(_citation_error_reason(exc)) from exc


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
    if len(excerpt) < MIN_CLAIM_LOCAL_SPAN_CHARS or excerpt not in shortest.citation_text:
        return None
    return (str(shortest.chunk_id), excerpt)


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


def _insert_passage_citation(
    cursor: psycopg.Cursor[Any],
    *,
    caller: CallerContext,
    run_id: UUID,
    index: int,
    citation: AnswerCitation,
    span: str,
    provenance: dict[str, object],
) -> UUID | None:
    """Run ``insert_run_citation_v2`` for one span attempt.

    Args:
        cursor: Open cursor inside the run transaction.
        caller: Server-derived caller.
        run_id: Admitted run.
        index: Write index within the run.
        citation: Passage citation.
        span: Span attempt, at most 1000 chars.
        provenance: Expand-only provenance jsonb.

    Returns:
        Inserted citation id, or None when the function returned no row.

    Raises:
        psycopg.Error: Any database rejection, including leaf resolution.
    """

    cursor.execute(
        """
        SELECT citation_id
        FROM app.insert_run_citation_v2(
          %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s::jsonb
        )
        """,
        (
            caller.user_id,
            caller.rpc_role(),
            caller.rpc_authorization_version(),
            str(run_id),
            index,
            citation.chunk_id,
            span[:1000],
            citation.paragraph_index,
            _json(provenance),
        ),
    )
    row = cursor.fetchone()
    return UUID(str(row[0])) if row is not None else None


def persist_answer_citations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    fusion: FusionResult,
    answer: AnswerPayload,
) -> CitationPersistResult:
    """Insert citation rows with fusion provenance. Expand-only on jsonb.

    Passage citations resolve one page-bounded leaf through
    ``insert_run_citation_v2``. A leaf-resolution failure retries once
    with the leading sentence, then skips that citation. Table citations
    keep the v1 path and still fail closed.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived caller. Used only to set the role.
        run_id: Admitted query run.
        fusion: Combined ranking result.
        answer: Verified answer.

    Returns:
        Inserted ids and skipped leaf-unresolved citations.

    Raises:
        QueryAdmissionError: Any non-leaf reason: ACL, replay, cap, chunk
            or span required, database error.

    Side Effects:
        Inserts into ``app.citations``. Does not create tables or columns.
        Writes are ordered by paragraph index, then original model order.
        Does not commit. Each passage attempt uses ``SAVEPOINT citation_leaf``.
    """

    ids: list[UUID] = []
    skipped: list[SkippedCitation] = []
    index = 0
    ordered_passages = sorted(
        enumerate(answer.citations),
        key=lambda item: (
            10_000 if item[1].paragraph_index is None else item[1].paragraph_index,
            item[0],
        ),
    )
    with connection.cursor() as cursor:
        for _, citation in ordered_passages:
            if index >= 12:
                raise QueryAdmissionError("answer_bounds_exceeded")
            span = (citation.span or "").strip()
            if not citation.chunk_id:
                raise QueryAdmissionError("chunk_required")
            if not span:
                raise QueryAdmissionError("citation_span_required")
            provenance = citation_provenance_payload(
                fusion=fusion,
                answer=answer,
                chunk_id=citation.chunk_id,
                table_id=citation.table_id,
                atomic_link_id=citation.atomic_link_id,
                inference=citation.inference,
                source_ranges=citation.source_ranges,
            )
            attempts: tuple[str, ...] = (span,)
            retry = leading_sentence(span)
            if retry:
                attempts = (span, retry)
            inserted: UUID | None = None
            last_reason = ""
            for attempt in attempts:
                cursor.execute("SAVEPOINT citation_leaf")
                try:
                    inserted = _insert_passage_citation(
                        cursor,
                        caller=caller,
                        run_id=run_id,
                        index=index,
                        citation=citation,
                        span=attempt,
                        provenance=provenance,
                    )
                except psycopg.Error as exc:
                    cursor.execute("ROLLBACK TO SAVEPOINT citation_leaf")
                    cursor.execute("RELEASE SAVEPOINT citation_leaf")
                    last_reason = _citation_error_reason(exc)
                    if last_reason not in LEAF_RESOLUTION_REASONS:
                        raise QueryAdmissionError(last_reason) from exc
                    continue
                cursor.execute("RELEASE SAVEPOINT citation_leaf")
                break
            if inserted is None:
                skipped.append(
                    SkippedCitation(
                        chunk_id=str(citation.chunk_id),
                        paragraph_index=citation.paragraph_index,
                        span=span,
                        reason=last_reason or "span_not_contained",
                    )
                )
                LOGGER.info(
                    "citation leaf unresolved",
                    extra={
                        "event": "query.verify.citation_leaf_unresolved",
                        "run_id": str(run_id),
                        "reason": last_reason,
                    },
                )
                continue
            ids.append(inserted)
            index += 1
        for citation in answer.table_citations:
            if index >= 12:
                raise QueryAdmissionError("answer_bounds_exceeded")
            provenance = citation_provenance_payload(
                fusion=fusion,
                answer=answer,
                chunk_id=citation.chunk_id,
                table_id=citation.table_id,
                atomic_link_id=citation.atomic_link_id,
                inference=citation.inference,
                source_ranges=citation.source_ranges,
            )
            snippet = (citation.span or "")[:500]
            try:
                cursor.execute(
                    """
                    SELECT citation_id
                    FROM app.insert_run_citation(
                      %s, %s, %s, %s, %s, %s::uuid, %s, %s::jsonb
                    )
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        str(run_id),
                        index,
                        citation.chunk_id,
                        snippet,
                        _json(provenance),
                    ),
                )
            except psycopg.Error as exc:
                _raise_citation_error(exc)
            row = cursor.fetchone()
            if row is not None:
                ids.append(UUID(str(row[0])))
            index += 1
    return CitationPersistResult(ids=tuple(ids), skipped=tuple(skipped))


def maybe_persist_verified_citations(
    connection: psycopg.Connection | None,
    *,
    caller: CallerContext | None,
    run_id: UUID | None,
    fusion: FusionResult,
    answer: AnswerPayload,
) -> CitationPersistResult:
    """Insert verified citations once per run when a durable connection exists.

    Args:
        connection: Per-run ``app_api`` connection. Skips when ``None``.
        caller: Server-derived caller for role context.
        run_id: Admitted query run.
        fusion: Combined ranking result for provenance jsonb.
        answer: Verified answer payload.

    Returns:
        Inserted ids and skipped citations, or an empty result when skipped
        because the graph is unbound, the answer has no citations, or rows
        already exist.

    Raises:
        QueryAdmissionError: Bound existence-check or persist failure. Callers
            must not treat this as a verified uncited success.

    Side Effects:
        Inserts into ``app.citations`` at most once per ``run_id``. Does not
        commit; the SSE consume loop commits after verify.
    """

    if connection is None or caller is None or run_id is None:
        return CitationPersistResult()
    if not answer.citations and not answer.table_citations:
        return CitationPersistResult()
    try:
        existing = list_run_citations(connection, caller=caller, run_id=run_id)
    except QueryAdmissionError:
        LOGGER.info(
            "citation persist existence check failed",
            extra={
                "event": "query.verify.citation_existence_check_failed",
                "run_id": str(run_id),
            },
        )
        raise
    except psycopg.Error as exc:
        LOGGER.info(
            "citation persist existence check failed",
            extra={
                "event": "query.verify.citation_existence_check_failed",
                "run_id": str(run_id),
            },
        )
        raise QueryAdmissionError("database_rejected") from exc
    if existing:
        return CitationPersistResult()
    try:
        return persist_answer_citations(
            connection,
            caller=caller,
            run_id=run_id,
            fusion=fusion,
            answer=answer,
        )
    except (psycopg.Error, QueryAdmissionError):
        LOGGER.info(
            "citation persist failed",
            extra={
                "event": "query.verify.citation_persist_failed",
                "run_id": str(run_id),
            },
        )
        raise


def persist_web_answer_citations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    sources: tuple[WebSourceRecord, ...],
    answer: AnswerPayload,
) -> tuple[UUID, ...]:
    """Insert verified Web citations. Company ``app.citations`` stay empty.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Query run.
        sources: Persisted Web sources for this run.
        answer: Verified answer with ``web_citations``.

    Returns:
        Inserted Web citation UUIDs.

    Raises:
        ValueError: If a span is not contained in the matching excerpt.
        QueryAdmissionError: Cap or ownership failure.
    """

    from smart_rag_core.web_research.store import insert_web_citation

    by_id = {item.web_source_id: item for item in sources}
    ids: list[UUID] = []
    for index, citation in enumerate(answer.web_citations):
        source = by_id.get(citation.web_source_id)
        if source is None:
            raise ValueError("web_evidence:not_found")
        ids.append(
            insert_web_citation(
                connection,
                caller=caller,
                run_id=run_id,
                citation_index=index,
                source=source,
                citation=citation,
            )
        )
    return tuple(ids)


def _json(payload: dict[str, object]) -> str:
    """Serialize provenance for jsonb insert.

    Args:
        payload: Provenance mapping.

    Returns:
        JSON text.
    """

    import json

    return json.dumps(payload, separators=(",", ":"), default=_default)


def _default(value: Any) -> str:
    """JSON fallback for UUID and similar values.

    Args:
        value: Non-JSON scalar.

    Returns:
        String form.
    """

    return str(value)
