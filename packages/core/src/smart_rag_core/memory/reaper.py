"""Dedicated query idempotency/event reaper. Independent of budget true-up."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True, slots=True)
class ReaperResult:
    """Counts from one reaper invocation.

    Attributes:
        keys_nulled: Completed-run idempotency keys set to NULL.
        events_deleted: Completed ``run_events`` rows removed.
        pending_keys_preserved: Active ``pending``/``running`` keys left intact.
        true_up_invoked: Always false. This reaper never settles reservations.
    """

    keys_nulled: int
    events_deleted: int
    pending_keys_preserved: int
    true_up_invoked: bool


def reap_query_run_retention(
    connection: psycopg.Connection,
    *,
    now: datetime | None = None,
) -> ReaperResult:
    """Reap completed idempotency keys (7d) and events (30d).

    Args:
        connection: Open connection. Caller should ``SET ROLE app_api`` or
            ``app_worker``.
        now: Injected clock. ``None`` uses database ``timezone('utc', now())``.

    Returns:
        Reaper counts. ``true_up_invoked`` is always false.

    Raises:
        psycopg.Error: When the SECURITY DEFINER function rejects the call.

    Side Effects:
        NULLs completed ``app.runs.idempotency_key`` rows older than seven
        days. Deletes completed ``app.run_events`` older than 30 days.
        Does not call ``app.true_up_query_reservation``.
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        if now is None:
            cursor.execute("SELECT * FROM app.reap_query_run_retention()")
        else:
            cursor.execute(
                "SELECT * FROM app.reap_query_run_retention(%s)",
                (now,),
            )
        row = cursor.fetchone()
    if row is None:
        return ReaperResult(0, 0, 0, False)
    return ReaperResult(
        keys_nulled=int(row["keys_nulled"]),
        events_deleted=int(row["events_deleted"]),
        pending_keys_preserved=int(row["pending_keys_preserved"]),
        true_up_invoked=bool(row["true_up_invoked"]),
    )


def enqueue_query_maintenance_jobs(
    connection: psycopg.Connection,
    *,
    now: datetime | None = None,
) -> int:
    """Enqueue the daily reaper and LangSmith-deletion worker jobs.

    Args:
        connection: Open worker or API connection.
        now: Injected clock for the daily idempotency key.

    Returns:
        Number of newly inserted jobs (0-2). Conflicts are no-ops.

    Side Effects:
        Inserts ``query_memory_reaper`` and ``langsmith_trace_deletion``
        ingestion_jobs rows without a budget reservation.
    """

    with connection.cursor() as cursor:
        if now is None:
            cursor.execute("SELECT app.enqueue_query_maintenance_jobs()")
        else:
            cursor.execute(
                "SELECT app.enqueue_query_maintenance_jobs(%s)",
                (now,),
            )
        row = cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


def search_conversation_lingering_ids(
    connection: psycopg.Connection,
    *,
    conversation_id: UUID,
) -> dict[str, int]:
    """Count conversation-scoped rows that must be gone after deletion.

    Args:
        connection: Open connection.
        conversation_id: Tombstoned conversation.

    Returns:
        Mapping of relation name to remaining row count. Tombstone
        ``app.conversations`` and content-free audit/usage are excluded.
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT relation_name, match_count FROM app.search_conversation_lingering_ids(%s)",
            (conversation_id,),
        )
        rows = cursor.fetchall()
    return {str(row["relation_name"]): int(row["match_count"]) for row in rows}
