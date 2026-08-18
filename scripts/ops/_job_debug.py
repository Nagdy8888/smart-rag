"""Print the in-flight scan job lease and checkpoint state."""

from __future__ import annotations

from uuid import UUID

import psycopg

JOB_ID = UUID("681cc466-9216-442a-ac7a-189328660316")
DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> None:
    """Print job and checkpoint rows."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        job = connection.execute(
            """
            SELECT status::text, attempt_count, lease_owner, lease_expires_at,
                   next_attempt_at, last_error, heartbeat_at, updated_at
            FROM app.ingestion_jobs
            WHERE id = %s
            """,
            (JOB_ID,),
        ).fetchone()
        print("job", job)
        checkpoints = connection.execute(
            """
            SELECT checkpoint_id, metadata ->> 'step' AS step
            FROM langgraph.checkpoints
            WHERE thread_id = %s::text
            ORDER BY checkpoint_id DESC
            LIMIT 4
            """,
            (JOB_ID,),
        ).fetchall()
        print("checkpoints", len(checkpoints))
        for row in checkpoints:
            print(row)


if __name__ == "__main__":
    main()
