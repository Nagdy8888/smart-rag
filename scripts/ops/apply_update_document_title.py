"""Apply the owner/admin document title RPC on hosted smart-rag.

Uses ``OPERATOR_SUPABASE_DB_URL`` and ``SET ROLE postgres``. Credentials
are never printed.
"""

from __future__ import annotations

from pathlib import Path
from typing import LiteralString, cast

import psycopg

REPO = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO / "supabase" / "migrations" / "20260921140000_update_document_title_v1.sql"
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
    """Apply the reviewed title-rename SQL and print signature proof.

    Returns:
        ``0`` on success. ``2`` when the operator DSN is missing.
        ``3`` when the function is not invoker or not app_api-only.
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
                'app.update_document_title(uuid,text,bigint,uuid,text)',
                'EXECUTE'
              ),
              has_function_privilege(
                'app_api',
                'app.update_document_title(uuid,text,bigint,uuid,text)',
                'EXECUTE'
              ),
              array_to_string(p.proconfig, ',')
            FROM pg_proc AS p
            INNER JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname = 'update_document_title'
            """
        ).fetchone()
        helper = connection.execute(
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
              ),
              array_to_string(p.proconfig, ',')
            FROM pg_proc AS p
            INNER JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app'
              AND p.proname = 'sync_document_title_search_terms'
            """
        ).fetchone()
    if row is None or helper is None:
        print("blocked=missing_function")
        return 3
    print(f"applied={MIGRATION.name}")
    print(f"signature={row[0]}")
    print(f"pronargs={row[1]}")
    print(f"prosecdef={row[2]}")
    print(f"public_execute={row[3]}")
    print(f"app_api_execute={row[4]}")
    print(f"search_path={row[5]}")
    print(f"helper_signature={helper[0]}")
    print(f"helper_pronargs={helper[1]}")
    print(f"helper_prosecdef={helper[2]}")
    print(f"helper_public_execute={helper[3]}")
    print(f"helper_app_api_execute={helper[4]}")
    print(f"helper_app_worker_execute={helper[5]}")
    print(f"helper_search_path={helper[6]}")
    if row[1] != 5 or row[2] is not False or row[3] is not False or row[4] is not True:
        print("blocked=signature_or_grants")
        return 3
    if (
        helper[1] != 2
        or helper[2] is not True
        or helper[3] is not False
        or helper[4] is not True
        or helper[5] is not True
        or "search_path=" not in str(helper[6] or "")
    ):
        print("blocked=helper_signature_or_grants")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
