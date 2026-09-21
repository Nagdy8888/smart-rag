"""Apply title search-term sync on hosted smart-rag.

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
    / "20260921150000_sync_document_title_search_terms_v1.sql"
)


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
    """Apply the reviewed title-term sync SQL and print signature proof.

    Returns:
        ``0`` on success. ``2`` when the operator DSN is missing.
        ``3`` when grants or invoker/definer flags are wrong.
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
              p.pronargs,
              p.prosecdef,
              has_function_privilege(
                'public',
                'app.sync_document_title_search_terms(uuid,text)',
                'EXECUTE'
              ),
              has_function_privilege(
                'app_api',
                'app.sync_document_title_search_terms(uuid,text)',
                'EXECUTE'
              ),
              has_function_privilege(
                'app_worker',
                'app.sync_document_title_search_terms(uuid,text)',
                'EXECUTE'
              )
            FROM pg_proc AS p
            INNER JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname = 'sync_document_title_search_terms'
            """
        ).fetchone()
        rename = connection.execute(
            """
            SELECT
              p.prosecdef,
              pg_get_functiondef(p.oid) LIKE
                '%sync_document_title_search_terms%'
            FROM pg_proc AS p
            INNER JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname = 'update_document_title'
            """
        ).fetchone()
    if row is None or rename is None:
        print("blocked=missing_function")
        return 3
    print(f"applied={MIGRATION.name}")
    print(f"signature={row[0]}")
    print(f"pronargs={row[1]}")
    print(f"prosecdef={row[2]}")
    print(f"public_execute={row[3]}")
    print(f"app_api_execute={row[4]}")
    print(f"app_worker_execute={row[5]}")
    print(f"rename_prosecdef={rename[0]}")
    print(f"rename_calls_sync={rename[1]}")
    if (
        row[1] != 2
        or row[2] is not True
        or row[3] is not False
        or row[4] is not True
        or row[5] is not True
        or rename[0] is not False
        or rename[1] is not True
    ):
        print("blocked=signature_or_grants")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
