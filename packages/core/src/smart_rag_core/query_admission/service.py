"""Postgres RPC wrappers for query-run admission and run-local budgets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, NoReturn, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
    QueryBudgetError,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole

_REASON_PREFIX = "query_admission:"


@dataclass(frozen=True, slots=True)
class QueryAdmissionResult:
    """Row returned by ``app.admit_query_run``.

    Attributes:
        context: Server-derived authorized runtime context.
        reconnect: Whether this call reused an existing paid run.
    """

    context: AuthorizedRuntimeContext
    reconnect: bool


@dataclass(frozen=True, slots=True)
class ReservationConsumeResult:
    """Optimistic consume outcome for one counted gateway call."""

    reservation_id: UUID
    optimistic_version: int
    remaining_usd: Decimal
    remaining_prompt_tokens: int
    remaining_completion_tokens: int


@dataclass(frozen=True, slots=True)
class TrueUpResult:
    """Idempotent settlement of one query reservation."""

    reservation_id: UUID
    status: str
    committed_amount_usd: Decimal
    already_settled: bool


def _raise_admission(exc: BaseException) -> NoReturn:
    """Map a Postgres exception to a typed admission/budget error.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always, with a stable reason when the SQL
            message includes a ``query_admission:`` prefix.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        reason = tail.split("\n")[0]
    if reason in {
        "optimistic_version_conflict",
        "reservation_exhausted",
        "reservation_not_active",
    }:
        raise QueryBudgetError(reason) from exc
    raise QueryAdmissionError(reason) from exc


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


def consume_query_reservation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    reservation_id: UUID,
    expected_version: int,
    amount_usd: Decimal,
    prompt_tokens: int,
    completion_tokens: int,
) -> ReservationConsumeResult:
    """Atomically consume run-local remaining USD and tokens.

    The SQL updates only ``app.budget_reservations`` by id and optimistic
    version. It does not lock ``company_settings`` or ``profiles``.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner of the run.
        reservation_id: Run-local reservation.
        expected_version: Optimistic version from the previous consume/admit.
        amount_usd: USD to deduct (estimated/max cap).
        prompt_tokens: Prompt tokens to deduct.
        completion_tokens: Completion tokens to deduct.

    Returns:
        New optimistic version and remaining holds.

    Raises:
        QueryBudgetError: On version conflict or insufficient remaining.

    Side Effects:
        Decrements remaining holds and increments ``optimistic_version``.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.consume_query_reservation(
                  %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    reservation_id,
                    expected_version,
                    amount_usd,
                    prompt_tokens,
                    completion_tokens,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        raise QueryBudgetError("consume_returned_no_row")
    return ReservationConsumeResult(
        reservation_id=row["reservation_id"],
        optimistic_version=int(row["optimistic_version"]),
        remaining_usd=Decimal(str(row["remaining_usd"])),
        remaining_prompt_tokens=int(row["remaining_prompt_tokens"]),
        remaining_completion_tokens=int(row["remaining_completion_tokens"]),
    )


def record_query_llm_usage(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    reservation_id: UUID,
    reservation_version: int,
    usage_kind: str,
    model_id: str,
    provider_attempt_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
    timeout_after_send: bool,
) -> UUID:
    """Append one immutable ``llm_usage`` row for a provider attempt.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner of the run.
        run_id: Admitted query run.
        reservation_id: Run-local reservation.
        reservation_version: Version observed at consume time.
        usage_kind: Allow-listed usage kind.
        model_id: Provider model identifier.
        provider_attempt_id: Idempotent attempt id.
        prompt_tokens: Actual or estimated prompt tokens.
        completion_tokens: Actual or estimated completion tokens.
        cost_usd: Actual or estimated USD.
        timeout_after_send: True when the HTTP response was lost after send.

    Returns:
        ``llm_usage.id``.

    Raises:
        QueryAdmissionError: When authorization or kind validation fails.

    Side Effects:
        Inserts an append-only usage row. Duplicate attempt ids are no-ops.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.record_query_llm_usage(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    reservation_id,
                    reservation_version,
                    usage_kind,
                    model_id,
                    provider_attempt_id,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    timeout_after_send,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("usage_returned_no_row")
    return UUID(str(row[0]))


def true_up_query_reservation(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    reservation_id: UUID,
) -> TrueUpResult:
    """Settle one reservation to the sum of immutable usage.

    A second call is an idempotent no-op.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner of the run.
        reservation_id: Reservation to settle.

    Returns:
        Committed amount and whether this call was already settled.

    Raises:
        QueryAdmissionError: When authorization fails.

    Side Effects:
        Sets reservation status to ``committed`` or ``released`` and stores
        ``committed_amount_usd``. Does not relock company/user budget rows.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.true_up_query_reservation(%s, %s, %s, %s)
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    reservation_id,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("true_up_returned_no_row")
    return TrueUpResult(
        reservation_id=row["reservation_id"],
        status=str(row["status"]),
        committed_amount_usd=Decimal(str(row["committed_amount_usd"])),
        already_settled=bool(row["already_settled"]),
    )


def heartbeat_query_run(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> datetime:
    """Record a durable heartbeat and extend the reservation TTL.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner of the run.
        run_id: Run to heartbeat.

    Returns:
        New ``heartbeat_at`` timestamp.

    Raises:
        QueryAdmissionError: When authorization or deadline checks fail.

    Side Effects:
        Updates ``app.runs.heartbeat_at`` and may extend reservation expiry.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.heartbeat_query_run(%s, %s, %s, %s)
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
        raise QueryAdmissionError("heartbeat_returned_no_row")
    return row[0]


def reconcile_expired_query_runs(
    connection: psycopg.Connection,
) -> int:
    """True-up and close expired pending/running query runs.

    Args:
        connection: Open connection as ``app_worker`` or ``app_api``.

    Returns:
        Number of runs settled by this invocation.

    Raises:
        QueryAdmissionError: When the RPC fails.

    Side Effects:
        Idempotently true-ups reservations and marks runs ``partial``. This is
        not the packet 7 idempotency/event reaper.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT app.reconcile_expired_query_runs()")
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        return 0
    return int(row[0])


def enqueue_query_reservation_true_up_job(
    connection: psycopg.Connection,
    *,
    now: datetime | None = None,
) -> UUID | None:
    """Enqueue one hourly ``query_reservation_true_up`` worker job.

    This is independent of the query-memory reaper. Duplicate calls in the
    same UTC hour are no-ops.

    Args:
        connection: Open ``app_worker`` or ``app_api`` connection.
        now: Injected clock. ``None`` uses UTC ``datetime.now``.

    Returns:
        Inserted job id, or ``None`` when the hourly idempotency key already
        exists.

    Side Effects:
        Inserts at most one ``app.ingestion_jobs`` row per UTC hour without
        a budget reservation.
    """

    clock = now or datetime.now(tz=UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    hour_key = clock.astimezone(UTC).strftime("%Y-%m-%dT%H")
    idempotency_key = f"query_reservation_true_up:{hour_key}"
    payload = json.dumps(
        {
            "kind": "query_reservation_true_up",
            "hour_key": hour_key,
        }
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.ingestion_jobs (
              job_kind,
              idempotency_key,
              payload_ref,
              priority,
              estimated_size_bytes
            )
            VALUES (
              'query_reservation_true_up',
              %s,
              %s::jsonb,
              'low'::app.job_priority,
              0
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (idempotency_key, payload),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return UUID(str(row[0]))


def record_run_restricted_evidence(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
    document_id: UUID,
    version_id: UUID,
    session_id: str,
    citation_id: UUID | None = None,
    purpose: Literal["evidence", "preview", "download"] = "evidence",
    signed_url_expires_at: datetime | None = None,
) -> UUID:
    """Append a content-minimized restricted-read event for a completed run.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived actor.
        run_id: Run that included the restricted evidence.
        document_id: Restricted document.
        version_id: Current version id.
        session_id: Bounded session identifier.
        citation_id: Optional citation row, never passage text.
        purpose: ``evidence``, ``preview``, or ``download``.
        signed_url_expires_at: Required only for ``download``.

    Returns:
        ``restricted_read_events.id``.

    Raises:
        QueryAdmissionError: When ACL, purpose, or caller checks fail.

    Side Effects:
        Calls the chained ``append_audit_event`` path and inserts one
        ``restricted_read_events`` row without passage text.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT app.record_run_restricted_evidence(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    run_id,
                    document_id,
                    version_id,
                    session_id,
                    citation_id,
                    purpose,
                    signed_url_expires_at,
                ),
            )
            row = cursor.fetchone()
    except psycopg.Error as exc:
        _raise_admission(exc)
    if row is None:
        raise QueryAdmissionError("restricted_evidence_returned_no_row")
    return UUID(str(row[0]))


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


def cancel_query_run(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> QueryRunRecord:
    """Cancel one owned pending/running query run and true-up its reservation.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Run to cancel.

    Returns:
        Updated run record with status ``cancelled``.

    Raises:
        QueryAdmissionError: When the caller does not own the run or it is
            not cancellable.

    Side Effects:
        Sets ``app.runs.status`` to ``cancelled`` and settles the reservation.
        Does not implement SSE cancel transport (packet 6).
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.cancel_query_run(%s, %s, %s, %s)
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


def fail_query_run(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    run_id: UUID,
) -> QueryRunRecord:
    """Mark one owned pending/running query run failed and settle its reservation.

    Args:
        connection: Open ``app_api`` connection.
        caller: Server-derived owner.
        run_id: Run to fail.

    Returns:
        Updated run record with status ``failed``.

    Raises:
        QueryAdmissionError: When the caller does not own the run or it is
            already terminal.

    Side Effects:
        Sets ``app.runs.status`` to ``failed`` and true-ups the reservation
        once. Idempotent when already ``failed``.
    """

    try:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM app.fail_query_run(%s, %s, %s, %s)
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
