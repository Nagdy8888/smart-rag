"""Print count-only P06-67 proof. Never prints titles or hashes."""

from __future__ import annotations

import argparse
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
    """Print current-copy, title-match, term, and job counts.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success. ``2`` when the operator DSN is missing.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", type=UUID, required=True)
    parser.add_argument("--version-id", type=UUID, required=True)
    parser.add_argument("--job-id", type=UUID, required=True)
    parser.add_argument("--title-file", type=Path, required=True)
    args = parser.parse_args(argv)
    resolved = args.title_file.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        print("blocked=title_file_not_private")
        return 2
    title = ""
    for raw in resolved.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            title = raw.strip()
            break
    if not title:
        print("blocked=empty_title")
        return 2
    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        print("missing_operator_url")
        return 2
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        docs = connection.execute(
            """
            SELECT
              count(*) FILTER (
                WHERE deleted_at IS NULL AND current_version_id IS NOT NULL
              ),
              count(*) FILTER (
                WHERE deleted_at IS NULL
                  AND current_version_id IS NOT NULL
                  AND title = %s
              ),
              count(*) FILTER (
                WHERE deleted_at IS NULL
                  AND current_version_id IS NOT NULL
                  AND length(title) = 24
              )
            FROM app.documents
            """,
            (title,),
        ).fetchone()
        version = connection.execute(
            """
            SELECT
              status::text,
              hybrid_verified_at IS NOT NULL,
              (
                SELECT count(*)
                FROM app.document_search_terms AS t
                INNER JOIN app.document_chunks AS c ON c.id = t.chunk_id
                WHERE c.version_id = v.id
                  AND c.deleted_at IS NULL
              )
            FROM app.document_versions AS v
            WHERE id = %s
            """,
            (args.version_id,),
        ).fetchone()
        job = connection.execute(
            """
            SELECT
              status::text,
              attempt_count,
              job_kind::text,
              last_error
            FROM app.ingestion_jobs
            WHERE id = %s
            """,
            (args.job_id,),
        ).fetchone()
        extra_versions = connection.execute(
            """
            SELECT count(*)
            FROM app.document_versions
            WHERE document_id = %s
              AND deleted_at IS NULL
            """,
            (args.document_id,),
        ).fetchone()
    print(f"current_documents={docs[0] if docs else None}")
    print(f"exact_title_current={docs[1] if docs else None}")
    print(f"old_24char_current={docs[2] if docs else None}")
    print(f"version_status={version[0] if version else None}")
    print(f"hybrid_verified={version[1] if version else None}")
    print(f"search_terms={version[2] if version else None}")
    print(f"versions_for_document={extra_versions[0] if extra_versions else None}")
    print(f"job_status={job[0] if job else None}")
    print(f"job_attempts={job[1] if job else None}")
    print(f"job_kind={job[2] if job else None}")
    print(f"job_error_present={bool(job[3]) if job else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
