"""Citation provenance payloads for existing ``app.citations.provenance`` jsonb."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.security.identity import CallerContext

LOGGER = logging.getLogger(__name__)


def citation_provenance_payload(
    *,
    fusion: FusionResult,
    answer: AnswerPayload,
    chunk_id: str | None,
    table_id: str | None,
    atomic_link_id: str | None,
    inference: bool,
) -> dict[str, object]:
    """Build expand-only provenance for one ``app.citations`` row.

    Fusion scores, algorithm, and config hash live in jsonb so packet 3
    does not require a new table.

    Args:
        fusion: Combined ranking result.
        answer: Verified answer.
        chunk_id: Canonical chunk when present.
        table_id: Canonical table when present.
        atomic_link_id: Owning atomic link.
        inference: True when the citation supports a composed inference.

    Returns:
        JSON-serializable provenance mapping.
    """

    scored = next(
        (item for item in fusion.evidence if item.chunk_id == chunk_id),
        None,
    )
    return {
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
    }


def persist_answer_citations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    fusion: FusionResult,
    answer: AnswerPayload,
) -> tuple[UUID, ...]:
    """Insert citation rows with fusion provenance. Expand-only on jsonb.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived caller. Used only to set the role.
        run_id: Admitted query run.
        fusion: Combined ranking result.
        answer: Verified answer.

    Returns:
        Inserted citation UUIDs.

    Side Effects:
        Inserts into ``app.citations``. Does not create tables or columns.
    """

    del caller
    ids: list[UUID] = []
    index = 0
    with connection.cursor() as cursor:
        for citation in (*answer.citations, *answer.table_citations):
            provenance = citation_provenance_payload(
                fusion=fusion,
                answer=answer,
                chunk_id=citation.chunk_id,
                table_id=citation.table_id,
                atomic_link_id=citation.atomic_link_id,
                inference=citation.inference,
            )
            snippet = (citation.span or "")[:500]
            cursor.execute(
                """
                INSERT INTO app.citations (
                  run_id, chunk_id, citation_index, snippet, provenance
                )
                VALUES (
                  %s::uuid,
                  %s::uuid,
                  %s,
                  %s,
                  %s::jsonb
                )
                RETURNING id
                """,
                (
                    str(run_id),
                    citation.chunk_id,
                    index,
                    snippet,
                    _json(provenance),
                ),
            )
            row = cursor.fetchone()
            if row is not None:
                ids.append(UUID(str(row[0])))
            index += 1
    return tuple(ids)


def maybe_persist_verified_citations(
    connection: psycopg.Connection | None,
    *,
    caller: CallerContext | None,
    run_id: UUID | None,
    fusion: FusionResult,
    answer: AnswerPayload,
) -> tuple[UUID, ...]:
    """Insert verified citations once per run when a durable connection exists.

    Args:
        connection: Per-run ``app_api`` connection. Skips when ``None``.
        caller: Server-derived caller for role context.
        run_id: Admitted query run.
        fusion: Combined ranking result for provenance jsonb.
        answer: Verified answer payload.

    Returns:
        Inserted citation UUIDs, or an empty tuple when skipped or already
        persisted.

    Side Effects:
        Inserts into ``app.citations`` at most once per ``run_id``. Does not
        commit; the SSE consume loop commits after verify.
    """

    if connection is None or caller is None or run_id is None:
        return ()
    if not answer.citations and not answer.table_citations:
        return ()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM app.citations
                WHERE run_id = %s::uuid
                LIMIT 1
                """,
                (str(run_id),),
            )
            if cursor.fetchone() is not None:
                return ()
    except psycopg.Error:
        LOGGER.info(
            "citation persist skipped",
            extra={
                "event": "query.verify.citation_existence_check_failed",
                "run_id": str(run_id),
            },
        )
        return ()
    try:
        return persist_answer_citations(
            connection,
            caller=caller,
            run_id=run_id,
            fusion=fusion,
            answer=answer,
        )
    except psycopg.Error:
        LOGGER.info(
            "citation persist skipped",
            extra={
                "event": "query.verify.citation_persist_failed",
                "run_id": str(run_id),
            },
        )
        return ()


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
