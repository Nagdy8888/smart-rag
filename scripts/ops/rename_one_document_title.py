"""Rename exactly one document through the owner/admin RPC.

The title is read from a gitignored file so production code stays
sample-blind. Prints counts only.
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
    """Rename one document as an owner and print title-length counts.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success. ``2`` on configuration failure. ``3`` when the
        RPC does not return the document id.
    """

    parser = argparse.ArgumentParser(description="Rename one document via RPC.")
    parser.add_argument("--document-id", type=UUID, required=True)
    parser.add_argument(
        "--title-file",
        type=Path,
        required=True,
        help="Gitignored file whose first non-empty line is the new title.",
    )
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
    if not title or len(title) > 512:
        print("blocked=invalid_private_title")
        return 2
    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        print("missing_operator_url")
        return 2
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        owner = connection.execute(
            """
            SELECT user_id, app.current_authorization_version()
            FROM app.profiles
            WHERE role = 'owner'::app.user_role
              AND disabled_at IS NULL
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if owner is None:
            print("blocked=no_owner")
            return 2
        before = connection.execute(
            """
            SELECT
              count(*) FILTER (
                WHERE deleted_at IS NULL AND current_version_id IS NOT NULL
              ),
              count(*) FILTER (
                WHERE deleted_at IS NULL AND length(title) = %s
              ),
              count(*) FILTER (
                WHERE deleted_at IS NULL AND title = %s
              )
            FROM app.documents
            """,
            (len(title), title),
        ).fetchone()
        row = connection.execute(
            "SELECT app.update_document_title(%s, %s, %s, %s, %s)",
            (owner[0], "owner", owner[1], args.document_id, title),
        ).fetchone()
        after = connection.execute(
            """
            SELECT
              count(*) FILTER (
                WHERE deleted_at IS NULL AND current_version_id IS NOT NULL
              ),
              count(*) FILTER (
                WHERE deleted_at IS NULL AND title = %s
              ),
              count(*) FILTER (
                WHERE deleted_at IS NULL
                  AND current_version_id IS NOT NULL
                  AND length(title) = 24
              ),
              (
                SELECT current_version_id::text
                FROM app.documents
                WHERE id = %s
              )
            FROM app.documents
            """,
            (title, args.document_id),
        ).fetchone()
    if row is None or row[0] is None:
        print("blocked=rename_not_found_or_forbidden")
        return 3
    print(f"renamed_document={row[0]}")
    print(f"title_chars={len(title)}")
    print(f"before_current={before[0] if before else None}")
    print(f"before_new_title_matches={before[2] if before else None}")
    print(f"after_current={after[0] if after else None}")
    print(f"after_new_title_matches={after[1] if after else None}")
    print(f"after_old_24char_current={after[2] if after else None}")
    print(f"current_version_id={after[3] if after else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
