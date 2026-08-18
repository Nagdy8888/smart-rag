"""Cancel the duplicate scan job and restart the Hybrid demo job cleanly."""

from __future__ import annotations

from uuid import UUID

import psycopg

DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
KEEP_JOB = UUID("681cc466-9216-442a-ac7a-189328660316")
DROP_JOB = UUID("a319f75c-1772-4f60-b0a2-868696e647ec")


def main() -> None:
    """Cancel the extra job, drop checkpoints, and requeue the demo job."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET
                  status = 'cancelled'::app.job_status,
                  lease_token = NULL,
                  lease_owner = NULL,
                  lease_expires_at = NULL
                WHERE id = %s
                """,
                (DROP_JOB,),
            )
            for job_id in (KEEP_JOB, DROP_JOB):
                cursor.execute(
                    "DELETE FROM langgraph.checkpoint_writes WHERE thread_id = %s",
                    (str(job_id),),
                )
                cursor.execute(
                    "DELETE FROM langgraph.checkpoint_blobs WHERE thread_id = %s",
                    (str(job_id),),
                )
                cursor.execute(
                    "DELETE FROM langgraph.checkpoints WHERE thread_id = %s",
                    (str(job_id),),
                )
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET
                  status = 'pending'::app.job_status,
                  next_attempt_at = timezone('utc', now()),
                  lease_token = NULL,
                  lease_owner = NULL,
                  lease_expires_at = NULL,
                  attempt_count = 0,
                  last_error = NULL,
                  payload_ref = COALESCE(payload_ref, '{}'::jsonb)
                    || jsonb_build_object(
                         'content_class', 'synthetic',
                         'review_approved', true
                       )
                WHERE id = %s
                RETURNING status::text, attempt_count
                """,
                (KEEP_JOB,),
            )
            row = cursor.fetchone()
        connection.commit()
    print(row)


if __name__ == "__main__":
    main()
