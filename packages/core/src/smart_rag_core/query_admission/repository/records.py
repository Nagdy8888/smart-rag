"""Query-run and citation record loaders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.repository.errors import _raise_admission
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole


@dataclass(frozen=True, slots=True)
class QueryRunRecord:
    """Authorized run fetch payload.

    Attributes:
        run_id: Run primary key.
        conversation_id: Owning conversation.
        creator_user_id: Run owner.
        status: Durable ``app.run_status`` text.
        reservation_id: Run-local reservation when present.
        created_at: Insert timestamp when returned.
    """

    run_id: UUID
    conversation_id: UUID
    creator_user_id: UUID
    status: str
    reservation_id: UUID | None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RunCitationRecord:
    """Citation identifiers without passage text.

    Attributes:
        citation_id: Citation row.
        citation_index: Display index.
        chunk_id: Canonical chunk when present.
        provenance: JSON object without source HTML.
        source_unavailable: True when the cited source was deleted.
    """

    citation_id: UUID
    citation_index: int
    chunk_id: UUID | None
    provenance: dict[str, object]
    source_unavailable: bool = False


def get_query_run(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> QueryRunRecord:
    """Fetch one run owned by the caller.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived identity.
        run_id: Run primary key.

    Returns:
        Run record. Foreign or missing runs raise ``not_found``.

    Raises:
        QueryAdmissionError: Authorization or lookup failure.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.get_query_run(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    reservation = row.get("reservation_id")
    return QueryRunRecord(
        run_id=row["id"],
        conversation_id=row["conversation_id"],
        creator_user_id=row["creator_user_id"],
        status=str(row["status"]),
        reservation_id=reservation,
        created_at=row.get("created_at"),
    )


def load_query_run_runtime(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> tuple[AuthorizedRuntimeContext, str]:
    """Rebuild authorized runtime and durable user text for resume.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Existing run.

    Returns:
        Authorized context plus the persisted user message.

    Raises:
        QueryAdmissionError: Missing run, foreign run, or missing user input.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.load_query_run_runtime(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("not_found")
    message = row.get("user_message")
    if not isinstance(message, str) or not message:
        raise QueryAdmissionError("input_missing")
    context = AuthorizedRuntimeContext(
        user_id=UUID(caller.user_id),
        role=UserRole(caller.rpc_role()),
        authorization_version=caller.rpc_authorization_version(),
        session_id=caller.session_id,
        conversation_id=row["conversation_id"],
        run_id=row["run_id"],
        reservation_id=row["reservation_id"],
        reconnect=True,
        route_family=Phase6RouteFamily(str(row["route_family"])),
        deadline_at=row["deadline_at"],
        recursion_limit=int(row["recursion_limit"]),
        correction_ceiling=int(row["correction_ceiling"]),
        subquestion_ceiling=int(row["subquestion_ceiling"]),
        model_call_ceiling=int(row["model_call_ceiling"]),
        tool_ceiling=int(row["tool_ceiling"]),
        discovery_ceiling=int(row["discovery_ceiling"]),
        manifest_ceiling=int(row["manifest_ceiling"]),
        side_effect_ceiling=int(row["side_effect_ceiling"]),
        reserved_amount_usd=Decimal(str(row["reserved_amount_usd"])),
        remaining_usd=Decimal(str(row["remaining_usd"])),
        remaining_prompt_tokens=int(row["remaining_prompt_tokens"]),
        remaining_completion_tokens=int(row["remaining_completion_tokens"]),
        optimistic_version=int(row["optimistic_version"]),
        heartbeat_at=row["heartbeat_at"],
        payload_hash=str(row["request_payload_hash"]),
        status=str(row["status"]),
    )
    return context, message


def list_run_citations(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> tuple[RunCitationRecord, ...]:
    """List citation IDs for an owned run. Passage text is omitted.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Run primary key.

    Returns:
        Citation identifiers and provenance maps.

    Raises:
        QueryAdmissionError: When the run is missing or not owned.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT citation_id, citation_index, chunk_id, provenance,
                       source_unavailable
                FROM app.list_run_citations(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                ),
            )
            rows = cursor.fetchall()
    except psycopg.Error as exc:
        _raise_admission(exc)
    records: list[RunCitationRecord] = []
    for row in rows:
        provenance_raw = row.get("provenance")
        provenance: dict[str, object] = (
            cast(dict[str, object], provenance_raw)
            if isinstance(provenance_raw, dict)
            else {}
        )
        chunk = row.get("chunk_id")
        unavailable = bool(row.get("source_unavailable"))
        chunk_id = None if unavailable or chunk is None else UUID(str(chunk))
        records.append(
            RunCitationRecord(
                citation_id=UUID(str(row["citation_id"])),
                citation_index=int(str(row["citation_index"])),
                chunk_id=chunk_id,
                provenance=provenance,
                source_unavailable=unavailable,
            )
        )
    return tuple(records)
