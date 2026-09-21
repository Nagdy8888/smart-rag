"""Reset one version status for a bounded operator reindex.

The parse path still admits only ``uploaded`` or ``scanning``. Already-indexed
statuses can refresh title search terms without this helper. Use it only
when a version was left in ``uploaded`` after a failed experiment. It does
not delete documents.
"""

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
    """Set one version status to uploaded.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success. ``2`` when the operator DSN or row is missing.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--version-id", type=UUID, required=True)
    parser.add_argument(
        "--status",
        choices=("uploaded", "graph_ineligible"),
        default="uploaded",
        help="Public version status to restore. Default uploaded.",
    )
    args = parser.parse_args(argv)
    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        print("missing_operator_url")
        return 2
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        row = connection.execute(
            """
            UPDATE app.document_versions
            SET
              status = %s::app.document_status,
              updated_at = timezone('utc', now())
            WHERE id = %s
            RETURNING status::text
            """,
            (args.status, args.version_id),
        ).fetchone()
    if row is None:
        print("blocked=version_missing")
        return 2
    print(f"version_status={row[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
