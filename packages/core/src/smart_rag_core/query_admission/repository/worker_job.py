"""Enqueue the hourly query-reservation true-up worker job."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import psycopg


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
