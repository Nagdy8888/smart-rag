"""Soft-delete listed documents through the owner delete RPC.

The id list is read from a gitignored file so production code stays
sample-blind. Prints identifiers and counts only, never titles.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[2]
BOOK_CONTENT_HASH = "72cdfc0f74bb1f60e0b61e950da06683e2db0aa04e90a59bdf271fcedfecf1f1"


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


def _load_ids(path: Path, *, keep: UUID) -> tuple[UUID, ...]:
    """Load document ids, refusing the canonical keep id.

    Args:
        path: Gitignored file with one UUID per line.
        keep: Document id that must not be deleted.

    Returns:
        Unique document ids in file order.

    Raises:
        ValueError: When the path is not private, the keep id is listed,
            or a line is not a UUID.
    """

    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise ValueError("ids_file_not_private")
    ids: list[UUID] = []
    seen: set[UUID] = set()
    for raw in resolved.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        document_id = UUID(line)
        if document_id == keep:
            raise ValueError("keep_id_listed")
        if document_id in seen:
            continue
        seen.add(document_id)
        ids.append(document_id)
    if not ids:
        raise ValueError("no_ids")
    return tuple(ids)


def main(argv: list[str] | None = None) -> int:
    """Soft-delete listed documents as an owner and print counts.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success. ``2`` on configuration failure. ``3`` when no
        owner profile exists.
    """

    parser = argparse.ArgumentParser(
        description="Soft-delete documents via app.delete_visible_document."
    )
    parser.add_argument(
        "--ids-file",
        type=Path,
        required=True,
        help="Gitignored file with one document UUID per line.",
    )
    parser.add_argument(
        "--keep",
        type=UUID,
        required=True,
        help="Canonical document id that must not appear in the id file.",
    )
    args = parser.parse_args(argv)
    try:
        document_ids = _load_ids(args.ids_file, keep=args.keep)
    except (OSError, ValueError) as exc:
        print(f"blocked={exc}")
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
            return 3
        for document_id in document_ids:
            version = connection.execute(
                "SELECT app.current_authorization_version()"
            ).fetchone()
            if version is None or version[0] is None:
                print("blocked=no_authorization_version")
                return 3
            row = connection.execute(
                """
                SELECT app.delete_visible_document(
                  %s::uuid, %s::text, %s::bigint, %s::uuid
                )
                """,
                (owner[0], "owner", version[0], document_id),
            ).fetchone()
            if row is None or row[0] is None:
                print(f"skipped_null={document_id}")
            else:
                print(f"deleted={row[0]}")
        current = connection.execute(
            """
            SELECT count(*)
            FROM app.documents
            WHERE deleted_at IS NULL
              AND current_version_id IS NOT NULL
            """
        ).fetchone()
        book = connection.execute(
            """
            SELECT count(*)
            FROM app.documents AS d
            JOIN app.document_versions AS v ON v.id = d.current_version_id
            WHERE d.deleted_at IS NULL
              AND v.content_hash = %s
            """,
            (BOOK_CONTENT_HASH,),
        ).fetchone()
    print(f"current_non_deleted={current[0] if current else None}")
    print(f"book_hash_current={book[0] if book else None}")
    print(f"kept={args.keep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
