"""Apply hosted overlay SQL migrations without printing credentials."""

from __future__ import annotations

from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = (
    REPO / "supabase" / "migrations" / "20260909120000_detector_findings_reviews_v1.sql",
    REPO / "supabase" / "migrations" / "20260909130000_heading_inventory_v1.sql",
    REPO / "supabase" / "migrations" / "20260909140000_dense_candidates_v2.sql",
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
    """Apply the three 2026-09-09 overlay migrations if tables are missing.

    Returns:
        Process exit code.
    """

    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        print("missing_operator_url")
        return 2
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        exists = connection.execute(
            "SELECT to_regclass('app.detector_findings') IS NOT NULL"
        ).fetchone()
        if exists is not None and bool(exists[0]):
            print("detector_findings_already_present=true")
            return 0
        for path in MIGRATIONS:
            print(f"applying={path.name}")
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                """
                INSERT INTO supabase_migrations.schema_migrations (version, name)
                VALUES (%s, %s)
                ON CONFLICT (version) DO NOTHING
                """,
                (path.name.split("_", 1)[0], path.stem),
            )
            print(f"applied={path.name}")
    with psycopg.connect(url, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        row = connection.execute(
            "SELECT to_regclass('app.detector_findings') IS NOT NULL"
        ).fetchone()
    print(f"detector_findings={bool(row[0]) if row is not None else False}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
