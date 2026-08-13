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


def test_comments_cannot_create_false_destructive_findings() -> None:
    """Documentation examples in SQL comments must not fail migration lint."""

    commented = """
        -- Never DROP TABLE app.documents.
        /* Never CREATE EXTENSION pg_search. */
        CREATE TABLE app.safe_addition (id uuid PRIMARY KEY);
    """

    assert find_migration_violations(commented, Path("comments.sql")) == []
