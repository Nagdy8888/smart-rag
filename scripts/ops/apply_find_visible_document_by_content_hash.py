"""Apply the visible content-hash lookup RPC on hosted smart-rag.

Uses ``OPERATOR_SUPABASE_DB_URL`` and ``SET ROLE postgres``. Credentials
are never printed.
"""

from __future__ import annotations

from pathlib import Path
from typing import LiteralString, cast

import psycopg

REPO = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO
    / "supabase"
    / "migrations"
    / "20260922100000_find_visible_document_by_content_hash_v1.sql"
)
_SIGNATURE = "app.find_visible_document_by_content_hash(uuid,text,bigint,text)"


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


def main() -> int:
    """Apply the content-hash lookup SQL and print grant proof.

    Returns:
        ``0`` on success. ``2`` when the operator DSN is missing.
        ``3`` when the function is not security definer or is executable
        by public.
    """

    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        print("missing_operator_url")
        return 2
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        print(f"applying={MIGRATION.name}")
        connection.execute(cast(LiteralString, MIGRATION.read_text(encoding="utf-8")))
        connection.execute(
            """
            INSERT INTO supabase_migrations.schema_migrations (version, name)
            VALUES (%s, %s)
            ON CONFLICT (version) DO NOTHING
            """,
            (MIGRATION.name.split("_", 1)[0], MIGRATION.stem),
        )
        row = connection.execute(
            """
            SELECT
              p.oid::regprocedure::text,
              p.prosecdef,
              has_function_privilege('public', %s, 'EXECUTE'),
              has_function_privilege('app_api', %s, 'EXECUTE')
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname = 'find_visible_document_by_content_hash'
            """,
            (_SIGNATURE, _SIGNATURE),
        ).fetchone()
    if row is None or not row[1] or row[2] or not row[3]:
        print(f"blocked=grant_proof row={row}")
        return 3
    print(f"installed={row[0]}")
    print("public_execute=false")
    print("app_api_execute=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
