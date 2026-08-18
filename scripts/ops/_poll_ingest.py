"""Poll one document version until a terminal public status."""

from __future__ import annotations

import json
import time
from uuid import UUID

import psycopg

VERSION_ID = UUID("b09fccc3-ca75-42d7-90fc-d05c8c9cef5d")
DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
TERMINAL = frozenset(
    {
        "graph_ineligible",
        "hybrid_ready",
        "graph_pending",
        "graph_ready",
        "failed",
    }
)


def main() -> int:
    """Print status transitions until terminal or timeout."""

    last = ""
    deadline = time.time() + 600
    while time.time() < deadline:
        with psycopg.connect(DB_URL, connect_timeout=10) as connection:
            version = connection.execute(
                """
                SELECT status::text, graph_eligible, hybrid_verified_at IS NOT NULL
                FROM app.document_versions
                WHERE id = %s
                """,
                (VERSION_ID,),
            ).fetchone()
            jobs = connection.execute(
                """
                SELECT job_kind, status::text, attempt_count, last_error
                FROM app.ingestion_jobs
                WHERE version_id = %s
                ORDER BY created_at
                """,
                (VERSION_ID,),
            ).fetchall()
            graph_jobs = connection.execute(
                """
                SELECT count(*)
                FROM app.lightrag_index_jobs
                WHERE version_id = %s
                """,
                (VERSION_ID,),
            ).fetchone()
        payload = {
            "version": version,
            "jobs": jobs,
            "lightrag_jobs": int(graph_jobs[0]) if graph_jobs else 0,
        }
        text = json.dumps(payload, default=str)
        if text != last:
            print(text, flush=True)
            last = text
        if version and version[0] in TERMINAL:
            return 0 if version[0] == "graph_ineligible" else 4
        time.sleep(4)
    print("timeout", flush=True)
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
