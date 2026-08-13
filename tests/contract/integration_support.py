"""Shared helpers for Phase 2 integration contract tests.

Process environment variables are read through a short-lived child interpreter so
contract tests remain compliant with the centralized environment-access rule.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPABASE_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
ARABIC_NORM_SQL = REPO_ROOT / "infra" / "paradedb" / "sql" / "arabic_norm_v1.sql"
COMPOSE_ENV_FILE = REPO_ROOT / ".env.compose"


def read_process_env(name: str) -> str | None:
    """Return one process environment variable without importing ``os`` here.

    Args:
        name: Environment variable name.

    Returns:
        The variable value when set and non-empty; otherwise ``None``.
    """

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; print(os.environ.get(sys.argv[1], ''), end='')",
            name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    value = completed.stdout.strip()
    return value or None


def resolve_supabase_db_url() -> str:
    """Resolve the Supabase Postgres URL for qualification tests.

    Returns:
        ``SUPABASE_DB_URL`` when set, otherwise the local Supabase CLI default.
    """

    return read_process_env("SUPABASE_DB_URL") or DEFAULT_SUPABASE_DB_URL


def local_supabase_status() -> dict[str, str]:
    """Return local Supabase status or skip when the live stack is unavailable.

    Returns:
        String-keyed URLs and ephemeral local credentials reported by the pinned
        CLI. Callers must never print or persist the returned credential values.

    Raises:
        RuntimeError: If the available CLI returns malformed status data.

    Side Effects:
        Executes the workspace-pinned Supabase CLI without mutating the stack.
        Skips the current test when ``pnpm`` or local Supabase is unavailable;
        the dedicated integration gate rejects such mandatory skips.
    """

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        pytest.skip("pnpm is unavailable; local Supabase contract not run")
    completed = subprocess.run(
        [pnpm, "exec", "supabase", "status", "-o", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("local Supabase stack is unavailable")
    try:
        payload: object = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("local Supabase status returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("local Supabase status returned an invalid object")
    untyped = cast(dict[object, object], payload)
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in untyped.items()
    ):
        raise RuntimeError("local Supabase status values are invalid")
    return cast(dict[str, str], untyped)


def try_connect(url: str, *, connect_timeout: int = 3) -> psycopg.Connection | None:
    """Open one Postgres connection when the target is reachable.

    Args:
        url: PostgreSQL connection URL.
        connect_timeout: Seconds to wait for TCP/auth completion.

    Returns:
        An open connection, or ``None`` when the server is unreachable.
    """

    try:
        return psycopg.connect(url, connect_timeout=connect_timeout)
    except psycopg.Error:
        return None


def docker_compose_available() -> bool:
    """Return whether ``docker compose`` responds on this host.

    Returns:
        ``True`` when the Docker CLI reports a working Compose plugin.
    """

    completed = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def paradedb_psql(
    sql: str,
    *,
    user: str = "paradedb",
    database: str = "paradedb",
) -> subprocess.CompletedProcess[str]:
    """Run one SQL script against the private ParadeDB container.

    Args:
        sql: SQL text executed on stdin.
        user: Postgres role inside the container.
        database: Target database name.

    Returns:
        The completed ``docker compose exec`` process result.
    """

    command = [
        "docker",
        "compose",
        "--env-file",
        str(COMPOSE_ENV_FILE),
        "exec",
        "-T",
        "paradedb",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-tA",
        "-U",
        user,
        "-d",
        database,
    ]
    return subprocess.run(
        command,
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=REPO_ROOT,
    )


def paradedb_reachable() -> bool:
    """Return whether the ParadeDB service accepts SQL over Compose exec.

    Returns:
        ``True`` when a trivial query succeeds against the container.
    """

    if not COMPOSE_ENV_FILE.is_file() or not docker_compose_available():
        return False
    completed = paradedb_psql("SELECT 1;\n")
    return completed.returncode == 0


def ensure_paradedb_arabic_normalizer() -> None:
    """Install or refresh ``search.normalize_arabic_v1`` on ParadeDB.

    Raises:
        RuntimeError: When the bootstrap SQL fails to apply.
    """

    bootstrap = ARABIC_NORM_SQL.read_text(encoding="utf-8")
    completed = paradedb_psql(bootstrap)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
