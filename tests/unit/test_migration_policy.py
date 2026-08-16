"""Unit tests for forward-only Supabase migration policy enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.check_migrations import find_migration_violations


@pytest.mark.parametrize(
    ("sql", "label"),
    [
        ("DROP TABLE app.documents;", "DROP TABLE"),
        ("ALTER TABLE app.documents DROP COLUMN title;", "DROP COLUMN"),
        ("DROP TYPE app.user_role;", "DROP TYPE"),
        (
            "ALTER TABLE app.documents ALTER COLUMN title "
            "TYPE varchar(5) USING title::varchar(5);",
            "ALTER ... TYPE narrowing",
        ),
        ("CREATE EXTENSION pg_search;", "CREATE EXTENSION pg_search"),
    ],
)
def test_destructive_migration_operations_fail_policy(sql: str, label: str) -> None:
    """Every forbidden migration family must produce a named violation."""

    violations = find_migration_violations(sql, Path("candidate.sql"))

    assert any(label in violation for violation in violations)


def test_security_definer_requires_explicit_search_path() -> None:
    """A privileged function without a fixed search path must fail policy."""

    unsafe = """
        CREATE FUNCTION private.unsafe() RETURNS void
        LANGUAGE sql SECURITY DEFINER AS $$ SELECT NULL; $$;
    """
    safe = """
        CREATE FUNCTION private.safe() RETURNS void
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
        AS $$ SELECT NULL; $$;
    """

    assert find_migration_violations(unsafe, Path("unsafe.sql"))
    assert find_migration_violations(safe, Path("safe.sql")) == []


def test_drop_check_constraint_is_allowed_for_additive_widening() -> None:
    """CHECK widening via DROP CONSTRAINT / ADD CONSTRAINT is expand-only."""

    sql = """
        ALTER TABLE app.budget_reservations
          DROP CONSTRAINT budget_reservations_kind_allowed;
        ALTER TABLE app.budget_reservations
          ADD CONSTRAINT budget_reservations_kind_allowed
          CHECK (reservation_kind IN ('ingestion_daily', 'query_run'));
    """

    assert find_migration_violations(sql, Path("widen_check.sql")) == []


def test_alter_table_drop_column_still_fails_policy() -> None:
    """Widening CHECK must not weaken the DROP COLUMN prohibition."""

    sql = "ALTER TABLE app.budget_reservations DROP COLUMN amount_usd;"
    violations = find_migration_violations(sql, Path("drop_column.sql"))

    assert any("DROP COLUMN" in item or "ALTER ... DROP" in item for item in violations)


def test_comments_cannot_create_false_destructive_findings() -> None:
    """Documentation examples in SQL comments must not fail migration lint."""

    commented = """
        -- Never DROP TABLE app.documents.
        /* Never CREATE EXTENSION pg_search. */
        CREATE TABLE app.safe_addition (id uuid PRIMARY KEY);
    """

    assert find_migration_violations(commented, Path("comments.sql")) == []
