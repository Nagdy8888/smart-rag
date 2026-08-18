"""List recent ingestion jobs and document versions."""

from __future__ import annotations

import json

import psycopg

DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def main() -> None:
    """Print recent jobs and versions."""

    with psycopg.connect(DB_URL, connect_timeout=10) as connection:
        jobs = connection.execute(
            """
            SELECT id::text, job_kind, status::text, attempt_count,
                   left(coalesce(last_error,''), 80), created_at, version_id::text
            FROM app.ingestion_jobs
            ORDER BY created_at DESC
            LIMIT 15
            """
        ).fetchall()
        versions = connection.execute(
            """
            SELECT id::text, document_id::text, status::text, graph_eligible, created_at
            FROM app.document_versions
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
    print("jobs", json.dumps(jobs, default=str, indent=2))
    print("versions", json.dumps(versions, default=str, indent=2))


if __name__ == "__main__":
    main()
