"""Citation provenance payloads for existing ``app.citations.provenance`` jsonb."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import psycopg

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import list_run_citations
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_fusion.models import FusionResult, ScoredPassage
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.security.identity import CallerContext

LOGGER = logging.getLogger(__name__)

_REASON_PREFIX = "query_citation:"


def _raise_citation_error(exc: BaseException) -> None:
    """Map a Postgres error to ``QueryAdmissionError``.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        reason = tail.split("\n")[0]
    raise QueryAdmissionError(reason) from exc


def ensure_fusion_source_citations(
    answer: AnswerPayload,
    *,
    fusion: FusionResult,
    tables: tuple[TableEvidenceRecord, ...],
) -> AnswerPayload:
    """Attach fusion/table citations when the model omitted structured sources.

    Live answer models often return prose without ``citations`` even though
    canonical passages were supplied in the prompt. The Sources tab and
    ``citation_preview`` SSE event rely on explicit citation rows.

    Args:
        answer: Verified or checked answer payload.
        fusion: Combined or Hybrid-effective evidence for this run.
        tables: Deterministic table snapshots from composition.

    Returns:
        The original payload when citations already exist, otherwise a copy
        citing every non-empty fusion passage and composed table snapshot.
    """

    if answer.citations or answer.table_citations:
        return answer
    citations = tuple(
        AnswerCitation(chunk_id=item.chunk_id, span=None)
        for item in fusion.evidence
        if item.citation_text.strip()
    )
    table_citations = tuple(
        AnswerCitation(
            table_id=item.table_id,
            source_ranges=item.source_ranges,
        )
        for item in tables
    )
    if not citations and not table_citations:
        return answer
    return answer.model_copy(
        update={
            "citations": citations,
            "table_citations": table_citations,
        }
    )


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
        key: value
        for key, value in payload.items()
        if value not in (None, "", (), [])
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
        if list_run_citations(connection, caller=caller, run_id=run_id):
            return ()
    except QueryAdmissionError:
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
    except (psycopg.Error, QueryAdmissionError):
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
