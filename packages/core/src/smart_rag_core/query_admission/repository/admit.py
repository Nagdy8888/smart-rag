"""Admit or reconnect one query run through ``app.admit_query_run``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.repository.errors import _raise_admission
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole


@dataclass(frozen=True, slots=True)
class QueryAdmissionResult:
    """Row returned by ``app.admit_query_run``.

    Attributes:
        context: Server-derived authorized runtime context.
        reconnect: Whether this call reused an existing paid run.
    """

    context: AuthorizedRuntimeContext
    reconnect: bool


def admit_query_run(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    idempotency_key: UUID,
    payload_hash: str,
    route_family: Phase6RouteFamily,
    token_issued_at: datetime | None = None,
) -> QueryAdmissionResult:
    """Admit one query run or reconnect through ``app.admit_query_run``.

    Args:
        connection: Open connection. Caller must ``SET ROLE app_api`` and
            commit on success.
        caller: Server-derived identity. Client role claims are not used.
        conversation_id: Conversation the caller must own.
        idempotency_key: Client-generated UUID message key.
        payload_hash: SHA-256 of the canonical payload.
        route_family: Server-selected family used only to look up ceilings.
        token_issued_at: JWT ``iat`` used with profile-wide session revocation.

    Returns:
        Authorized runtime context plus reconnect flag.

    Raises:
        QueryAdmissionError: When authorization, ownership, budget,
            concurrency, or idempotency checks fail.

    Side Effects:
        Inserts one ``app.runs`` row and one ``query_run`` reservation unless
        this is an authorized reconnect.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.admit_query_run(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    conversation_id,
                    str(idempotency_key),
                    payload_hash,
                    route_family.value,
                    caller.session_id,
                    token_issued_at,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("admit_returned_no_row")
    context = AuthorizedRuntimeContext(
        user_id=UUID(caller.user_id),
        role=UserRole(caller.rpc_role()),
        authorization_version=caller.rpc_authorization_version(),
        session_id=caller.session_id,
        conversation_id=conversation_id,
        run_id=row["run_id"],
        reservation_id=row["reservation_id"],
        reconnect=bool(row["reconnect"]),
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
    return QueryAdmissionResult(context=context, reconnect=context.reconnect)
