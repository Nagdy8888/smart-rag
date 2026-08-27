"""Heartbeat, reconcile, cancel, and fail RPCs for query runs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.repository.errors import raise_admission
from smart_rag_core.query_admission.repository.records import QueryRunRecord
from smart_rag_core.security.identity import CallerContext


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
        raise_admission(exc)
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
        raise_admission(exc)
    if row is None:
        return 0
    return int(row[0])


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
        raise_admission(exc)
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
        raise_admission(exc)
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
