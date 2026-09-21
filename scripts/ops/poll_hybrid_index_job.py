"""Poll one hybrid_index job until it reaches a terminal status."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[2]


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one gitignored env file.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to values.
    """

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main(argv: list[str] | None = None) -> int:
    """Poll job and version counts until the job is terminal.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` when the job completed. ``2`` on configuration failure.
        ``3`` on timeout or non-complete terminal status.
    """

    parser = argparse.ArgumentParser(description="Poll one hybrid_index job.")
    parser.add_argument("--job-id", type=UUID, required=True)
    parser.add_argument("--wait-seconds", type=int, default=5400)
    args = parser.parse_args(argv)
    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        print("missing_operator_url")
        return 2
    deadline = time.monotonic() + args.wait_seconds
    terminal = None
    while time.monotonic() < deadline:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute("SET ROLE postgres")
            row = connection.execute(
                """
                SELECT
                  j.status::text,
                  j.attempt_count,
                  left(coalesce(j.last_error, ''), 160),
                  dv.status::text,
                  dv.hybrid_verified_at,
                  (
                    SELECT count(*)
                    FROM app.document_search_terms AS t
                    INNER JOIN app.document_chunks AS c ON c.id = t.chunk_id
                    WHERE c.version_id = dv.id
                      AND c.deleted_at IS NULL
                  )
                FROM app.ingestion_jobs AS j
                INNER JOIN app.document_versions AS dv ON dv.id = j.version_id
                WHERE j.id = %s
                """,
                (args.job_id,),
            ).fetchone()
        if row is None:
            print("blocked=job_missing")
            return 3
        print(
            "poll "
            f"job_status={row[0]} attempts={row[1]} version_status={row[3]} "
            f"hybrid_verified={row[4]} terms={row[5]} error={row[2]!r}"
        )
        version_ready = row[3] in {
            "hybrid_ready",
            "graph_ineligible",
            "graph_pending",
            "graph_ready",
        }
        if row[0] == "completed" and version_ready:
            terminal = row
            break
        if row[0] in {"failed", "dead_letter", "cancelled"}:
            terminal = row
            break
        time.sleep(20)
    if terminal is None:
        print("blocked=wait_timeout")
        return 3
    print(f"terminal_job_status={terminal[0]}")
    print(f"terminal_attempts={terminal[1]}")
    print(f"terminal_last_error={terminal[2]}")
    print(f"terminal_version_status={terminal[3]}")
    print(f"terminal_hybrid_verified={terminal[4]}")
    print(f"terminal_terms={terminal[5]}")
    if terminal[0] != "completed":
        print("blocked=hybrid_index_not_completed")
        return 3
    if terminal[3] not in {
        "hybrid_ready",
        "graph_ineligible",
        "graph_pending",
        "graph_ready",
    }:
        print("blocked=version_not_ready")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
