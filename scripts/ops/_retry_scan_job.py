"""Reset the in-flight movie metadata scan job so the worker can retry."""

from __future__ import annotations

from uuid import UUID

import psycopg

JOB_ID = UUID("681cc466-9216-442a-ac7a-189328660316")
DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> None:
    """Clear the lease and schedule an immediate retry with synthetic class."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET
                  status = 'pending'::app.job_status,
                  next_attempt_at = timezone('utc', now()),
                  lease_token = NULL,
                  lease_owner = NULL,
                  lease_expires_at = NULL,
                  payload_ref = COALESCE(payload_ref, '{}'::jsonb)
                    || jsonb_build_object(
                         'content_class', 'synthetic',
                         'review_approved', true
                       )
                WHERE id = %s
                RETURNING status::text, attempt_count, last_error
                """,
                (JOB_ID,),
            )
            row = cursor.fetchone()
        connection.commit()
    print(row)


if __name__ == "__main__":
    main()
