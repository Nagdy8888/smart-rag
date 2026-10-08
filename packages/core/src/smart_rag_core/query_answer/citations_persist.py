"""Split from ``citations.py`` so each runtime module stays within the line cap."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import list_run_citations
from smart_rag_core.query_answer.citations_leaf import (
    CitationPersistResult,
    SkippedCitation,
    citation_error_reason,
    citation_provenance_payload,
    leading_sentence,
    raise_citation_error,
)
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.web_research.models import WebSourceRecord

LOGGER = logging.getLogger(__name__)

LEAF_RESOLUTION_REASONS = frozenset(
    {"span_not_contained", "leaf_ambiguous", "page_ambiguous"}
)


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
                    last_reason = citation_error_reason(exc)
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
                raise_citation_error(exc)
            row = cursor.fetchone()
            if row is not None:
                ids.append(UUID(str(row[0])))
            index += 1
    return CitationPersistResult(ids=tuple(ids), skipped=tuple(skipped))


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


def _default(value: Any) -> str:
    """JSON fallback for UUID and similar values.

    Args:
        value: Non-JSON scalar.

    Returns:
        String form.
    """

    return str(value)


def _json(payload: dict[str, object]) -> str:
    """Serialize provenance for jsonb insert.

    Args:
        payload: Provenance mapping.

    Returns:
        JSON text.
    """

    import json

    return json.dumps(payload, separators=(",", ":"), default=_default)
