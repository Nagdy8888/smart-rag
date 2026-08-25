"""Destructive local gate for deterministic Supabase resets and generated types."""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from schema_fingerprint import (
    SchemaFingerprint,
    assert_required_inventory,
    capture_schema_fingerprint,
    fingerprints_match,
    generated_types_match,
    inventory_counts,
    normalize_generated_types,
    schema_fingerprint_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_TYPES = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "generated"
    / "database.ts"
)
LOCAL_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
TYPE_SCHEMAS = "app,public,storage,auth"


def _refuse_hosted_destructive_dsn(url: str) -> None:
    """Refuse destructive resets against hosted Supabase.

    Args:
        url: Candidate Postgres DSN. Never logged.

    Raises:
        RuntimeError: If the host is hosted Supabase. The message never
            includes the DSN.
    """

    host = (urlparse(url).hostname or "").casefold()
    if host.endswith(".supabase.co") or host.endswith("pooler.supabase.com"):
        raise RuntimeError("destructive_tests_refuse_hosted_supabase")


def _required_executable(name: str) -> str:
    """Resolve one required executable to an absolute host path.

    Args:
        name: Executable name accepted by :func:`shutil.which`.

    Returns:
        Absolute executable path.

    Raises:
        RuntimeError: If the executable is unavailable.
    """

    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(f"Required executable is unavailable: {name}")
    return executable


def _run(command: list[str], label: str) -> str:
    """Run one bounded local gate command and return its standard output.

    Args:
        command: Executable and arguments. The executable is resolved before
            this function is called.
        label: Sanitized operation label for diagnostics.

    Returns:
        Captured standard output.

    Raises:
        RuntimeError: If the command exits non-zero.

    Side Effects:
        Executes a child process from the repository root.
    """

    completed = subprocess.run(  # noqa: S603 - fixed local tool commands only.
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"{label} failed with exit {completed.returncode}: {diagnostic}"
        )
    return completed.stdout


def _reset_local_database(pnpm: str, pass_number: int) -> None:
    """Reset the local database from migrations for one proof pass.

    Args:
        pnpm: Absolute workspace package-runner executable.
        pass_number: One-based reset pass number used only in diagnostics.

    Side Effects:
        Destructively recreates the local Supabase database and applies every
        checked-in migration.
    """

    _run(
        [
            pnpm,
            "exec",
            "supabase",
            "db",
            "reset",
            "--local",
            "--yes",
        ],
        f"Supabase reset pass {pass_number}",
    )


def _capture_fingerprint() -> SchemaFingerprint:
    """Capture and validate the post-reset local database inventory.

    Returns:
        Validated schema fingerprint.

    Raises:
        psycopg.Error: If the reset database cannot be queried.
        AssertionError: If required Phase 2 objects or denials are missing.

    Side Effects:
        Opens a short-lived read-only PostgreSQL transaction.
    """

    with psycopg.connect(LOCAL_DB_URL, connect_timeout=5) as connection:
        connection.read_only = True
        fingerprint = capture_schema_fingerprint(connection)
        assert_required_inventory(fingerprint)
        connection.rollback()
        return fingerprint


def _generate_types(pnpm: str) -> str:
    """Generate canonical local Supabase TypeScript definitions in memory.

    Args:
        pnpm: Absolute workspace package-runner executable.

    Returns:
        Line-ending-normalized generated TypeScript.

    Side Effects:
        Runs the pinned Supabase CLI against the host-published local Postgres
        URL (``127.0.0.1:54322``) without writing the generated file. ``--local``
        is avoided because prior phases observed it targeting container port
        ``5432``.
    """

    source = _run(
        [
            pnpm,
            "exec",
            "supabase",
            "gen",
            "types",
            "typescript",
            "--db-url",
            LOCAL_DB_URL,
            "--schema",
            TYPE_SCHEMAS,
        ],
        "Supabase type generation",
    )
    return normalize_generated_types(source)


def _run_schema_contract(pytest: str, pass_number: int) -> None:
    """Run authoritative schema invariants after one clean reset.

    Args:
        pytest: Absolute pytest executable.
        pass_number: One-based reset pass number used only in diagnostics.

    Side Effects:
        Executes the schema contract test against the local database.
    """

    _run(
        [pytest, "-q", "tests/contract/test_schema_reset.py"],
        f"Schema contract pass {pass_number}",
    )


def _schema_difference(first: SchemaFingerprint, second: SchemaFingerprint) -> str:
    """Build a bounded readable diff for the first changed inventory.

    Args:
        first: Inventory captured after reset one.
        second: Inventory captured after reset two.

    Returns:
        At most 120 unified-diff lines for the first differing inventory.
    """

    for name in sorted(first):
        if first[name] == second[name]:
            continue
        first_lines = json.dumps(first[name], ensure_ascii=False, indent=2).splitlines()
        second_lines = json.dumps(
            second[name], ensure_ascii=False, indent=2
        ).splitlines()
        difference = difflib.unified_diff(
            first_lines,
            second_lines,
            fromfile=f"reset-1/{name}",
            tofile=f"reset-2/{name}",
            lineterm="",
        )
        return "\n".join(list(difference)[:120])
    return "Schema fingerprints differ outside the named inventories."


def _sha256_text(value: str) -> str:
    """Return the hexadecimal SHA-256 digest of UTF-8 text.

    Args:
        value: Text to hash.

    Returns:
        Lowercase hexadecimal digest.
    """

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    """Run two destructive resets and compare schema and generated outputs.

    Returns:
        ``0`` when both resets, schema contracts, fingerprints, and generated
        types are identical and match the checked-in type artifact; ``1`` on
        any failure.

    Side Effects:
        Destructively resets the local Supabase database exactly twice, runs
        contract tests, and generates TypeScript definitions in memory.
    """

    try:
        _refuse_hosted_destructive_dsn(LOCAL_DB_URL)
        pnpm = _required_executable("pnpm")
        pytest = _required_executable("pytest")
        committed_types = normalize_generated_types(
            GENERATED_TYPES.read_text(encoding="utf-8")
        )

        fingerprints: list[SchemaFingerprint] = []
        generated_outputs: list[str] = []
        for pass_number in (1, 2):
            _reset_local_database(pnpm, pass_number)
            fingerprint = _capture_fingerprint()
            generated = _generate_types(pnpm)
            _run_schema_contract(pytest, pass_number)
            if not generated_types_match(generated, committed_types):
                raise AssertionError(
                    "Generated types drift after reset "
                    f"{pass_number}: generated={_sha256_text(generated)} "
                    f"committed={_sha256_text(committed_types)}"
                )
            fingerprints.append(fingerprint)
            generated_outputs.append(generated)
            counts = ", ".join(
                f"{name}={count}" for name, count in inventory_counts(fingerprint)
            )
            print(
                f"reset={pass_number} "
                f"schema_sha256={schema_fingerprint_sha256(fingerprint)} "
                f"types_sha256={_sha256_text(generated)} {counts}"
            )

        if not fingerprints_match(fingerprints[0], fingerprints[1]):
            raise AssertionError(
                "Schema fingerprint drift between resets:\n"
                + _schema_difference(fingerprints[0], fingerprints[1])
            )
        if not generated_types_match(generated_outputs[0], generated_outputs[1]):
            raise AssertionError("Generated TypeScript differs between resets")
    except (AssertionError, OSError, psycopg.Error, RuntimeError) as exc:
        print(f"Schema determinism gate failed: {exc}", file=sys.stderr)
        return 1

    print("Schema determinism gate passed after two clean local resets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
