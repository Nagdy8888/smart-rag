"""Expand/contract migration policy checks for Phase 2 schema migrations."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"

ALLOWED_MIGRATION_PREFIXES = (
    "20260812131227_pgvector_gate_and_arabic_norm_v1.sql",
    "20260812135034_app_schemas_enums_job_columns_v1.sql",
    "20260812135038_profiles_company_invitations_v1.sql",
    "20260812135041_documents_sources_acl_v1.sql",
    "20260812135045_document_chunks_tables_search_v1.sql",
    "20260812135049_durable_jobs_v1.sql",
    "20260812135053_lightrag_maps_v1.sql",
    "20260812135056_conversations_messages_runs_v1.sql",
    "20260812135100_tools_catalog_v1.sql",
    "20260812135104_llm_usage_budgets_v1.sql",
    "20260812135107_audit_events_v1.sql",
    "20260812135111_langgraph_lightrag_private_v1.sql",
    "20260812135115_indexes_rls_grants_v1.sql",
)

DESTRUCTIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "DROP TABLE"),
    (re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE), "DROP COLUMN"),
    (re.compile(r"\bDROP\s+TYPE\b", re.IGNORECASE), "DROP TYPE"),
    (re.compile(r"\bALTER\s+TABLE\b[^;]*\bDROP\b", re.IGNORECASE), "ALTER ... DROP"),
    (
        re.compile(
            r"\bALTER\s+COLUMN\b[^;]*\bTYPE\b[^;]*\bUSING\b",
            re.IGNORECASE,
        ),
        "ALTER ... TYPE narrowing",
    ),
    (
        re.compile(r"\bCREATE\s+EXTENSION\b[^;]*\bpg_search\b", re.IGNORECASE),
        "CREATE EXTENSION pg_search on Supabase",
    ),
)

SECURITY_DEFINER_PATTERN = re.compile(
    r"SECURITY\s+DEFINER",
    re.IGNORECASE,
)
SEARCH_PATH_PATTERN = re.compile(
    r"SET\s+search_path\s*=",
    re.IGNORECASE,
)


def _strip_sql_comments(sql: str) -> str:
    """Remove block and line comments before static policy scanning."""

    without_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", without_block)


def _validate_security_definer(sql: str, path: Path, violations: list[str]) -> None:
    """Require explicit search_path on every SECURITY DEFINER function."""

    for match in SECURITY_DEFINER_PATTERN.finditer(sql):
        start = max(0, match.start() - 400)
        end = min(len(sql), match.end() + 400)
        window = sql[start:end]
        if not SEARCH_PATH_PATTERN.search(window):
            violations.append(
                f"{path.name}: SECURITY DEFINER without SET search_path near offset {match.start()}"
            )


def main() -> int:
    """Validate Phase 2 migration expand/contract policy.

    Returns:
        ``0`` when all migration files pass policy checks; ``1`` otherwise.
    """

    if not MIGRATIONS.is_dir():
        print("No supabase/migrations directory", file=sys.stderr)
        return 1

    files = sorted(p for p in MIGRATIONS.glob("*.sql") if p.is_file())
    if not files:
        print("No migration files found", file=sys.stderr)
        return 1

    unknown = [
        path.name for path in files if path.name not in ALLOWED_MIGRATION_PREFIXES
    ]
    if unknown:
        print(
            "Unexpected migration files (update allowlist after review): "
            + ", ".join(unknown),
            file=sys.stderr,
        )
        return 1

    violations: list[str] = []
    for path in files:
        raw = path.read_text(encoding="utf-8")
        sql = _strip_sql_comments(raw)
        for pattern, label in DESTRUCTIVE_PATTERNS:
            if pattern.search(sql):
                violations.append(f"{path.name}: forbidden {label}")
        _validate_security_definer(sql, path, violations)

    if violations:
        for item in violations:
            print(item, file=sys.stderr)
        return 1

    print(f"Phase 2 migration policy OK ({len(files)} reviewed files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
