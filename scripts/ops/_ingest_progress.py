"""Inspect scan/promotion progress for the demo CSV job."""

from __future__ import annotations

from uuid import UUID

import psycopg

JOB_ID = UUID("681cc466-9216-442a-ac7a-189328660316")
VERSION_ID = UUID("b09fccc3-ca75-42d7-90fc-d05c8c9cef5d")
DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> None:
    """Print scan events, saga rows, and checkpoint channels."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        job = connection.execute(
            """
            SELECT status::text, attempt_count, heartbeat_at, lease_expires_at,
                   left(coalesce(last_error, ''), 60)
            FROM app.ingestion_jobs WHERE id = %s
            """,
            (JOB_ID,),
        ).fetchone()
        print("job", job)
        version = connection.execute(
            """
            SELECT status::text, graph_eligible, current_storage_bucket, current_storage_path
            FROM app.document_versions WHERE id = %s
            """,
            (VERSION_ID,),
        ).fetchone()
        print("version", version)
        scans = connection.execute(
            """
            SELECT result::text, bytes_examined, scanned_at, left(details::text, 80)
            FROM app.document_scan_events
            WHERE version_id = %s
            ORDER BY scanned_at
            """,
            (VERSION_ID,),
        ).fetchall()
        print("scans", scans)
        sagas = connection.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'app' AND table_name LIKE '%promo%'
            """
        ).fetchall()
        print("promo_tables", sagas)
        for table in sagas:
            name = table[0]
            rows = connection.execute(
                f"SELECT * FROM app.{name} WHERE version_id = %s OR saga_idempotency_key LIKE %s LIMIT 5",  # noqa: S608
                (VERSION_ID, f"%{JOB_ID}%"),
            ).fetchall()
            print(name, rows)
        channels = connection.execute(
            """
            SELECT checkpoint_id, channel, type
            FROM langgraph.checkpoint_writes
            WHERE thread_id = %s::text
            ORDER BY checkpoint_id, idx
            """,
            (JOB_ID,),
        ).fetchall()
        print("writes", channels)
        nxt = connection.execute(
            """
            SELECT checkpoint->>'ts', jsonb_object_keys(checkpoint)
            FROM langgraph.checkpoints
            WHERE thread_id = %s::text
            ORDER BY checkpoint_id DESC
            LIMIT 1
            """,
            (JOB_ID,),
        ).fetchall()
        print("latest_keys", nxt)


if __name__ == "__main__":
    main()
