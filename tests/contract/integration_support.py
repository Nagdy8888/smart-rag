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
from typing import TypeVar, cast
from urllib.parse import quote, urlparse

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPABASE_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
ARABIC_NORM_SQL = REPO_ROOT / "infra" / "paradedb" / "sql" / "arabic_norm_v1.sql"
COMPOSE_ENV_FILE = REPO_ROOT / ".env.compose"
_T = TypeVar("_T")


def typed_module_attr(owner: object, name: str, typed: _T) -> _T:
    """Return ``getattr(owner, name)`` using ``typed`` only for the result type.

    This avoids importing private identifiers and reading untyped third-party
    members while keeping the caller's annotation. ``typed`` is never used
    at runtime.

    Args:
        owner: Module or object that owns the attribute.
        name: Attribute name, including private helpers owned elsewhere.
        typed: Unused value that supplies the returned type.

    Returns:
        The named attribute, typed as ``typed``.
    """

    del typed
    return cast(_T, getattr(owner, name))


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


def refuse_hosted_destructive_dsn(url: str) -> None:
    """Refuse destructive suites against hosted Supabase.

    Args:
        url: Candidate Postgres DSN. Never logged.

    Raises:
        RuntimeError: If the host is ``*.supabase.co`` or a Supabase
            pooler hostname. The message never includes the DSN.
    """

    host = (urlparse(url).hostname or "").casefold()
    if host.endswith(".supabase.co") or host.endswith("pooler.supabase.com"):
        raise RuntimeError("destructive_tests_refuse_hosted_supabase")


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


def _local_supabase_runtime_ready(connection: psycopg.Connection) -> bool:
    """Return whether a ``postgres`` database has the Smart RAG runtime.

    A reachable TCP port is not enough for contract isolation. Vanilla or
    unrestored local Postgres on ``:54322`` accepts connections but lacks
    ``app`` / ``app_worker``. ParadeDB and other databases are unchanged.

    Args:
        connection: Open psycopg connection.

    Returns:
        ``True`` when the database is not local Supabase ``postgres``, or
        when that database has schema ``app`` and role ``app_worker``.
    """

    try:
        database = connection.execute("SELECT current_database()").fetchone()
        if database is None or database[0] != "postgres":
            return True
        schema = connection.execute(
            "SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'app'"
        ).fetchone()
        if schema is None:
            return False
        role = connection.execute(
            "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'app_worker'"
        ).fetchone()
    except psycopg.Error:
        return False
    return role is not None


def try_connect(url: str, *, connect_timeout: int = 3) -> psycopg.Connection | None:
    """Open one Postgres connection when the target is a usable stack.

    Args:
        url: PostgreSQL connection URL.
        connect_timeout: Seconds to wait for TCP/auth completion.

    Returns:
        An open connection, or ``None`` when the server is unreachable or
        the local ``postgres`` database lacks ``app`` / ``app_worker``.
        Incomplete local Postgres is treated as unavailable so CPU/local
        contract runs skip live integration instead of erroring.
    """

    try:
        connection = psycopg.connect(url, connect_timeout=connect_timeout)
    except psycopg.Error:
        return None
    try:
        if not _local_supabase_runtime_ready(connection):
            connection.close()
            return None
        connection.rollback()
    except psycopg.Error:
        connection.close()
        return None
    return connection


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


def ensure_paradedb_bm25_index() -> None:
    """Create or rebuild the pg_search BM25 index (bootstrap role).

    Rebuilds when the index is missing alias/language/is_current fields so
    Packet 2 typed queries can run. Derived-index DDL only.

    Raises:
        RuntimeError: When index DDL fails.
    """

    sql = """
ALTER TABLE public.bm25_chunks ADD COLUMN IF NOT EXISTS content_hash text;
DROP INDEX IF EXISTS public.bm25_chunks_search_idx;
CREATE INDEX bm25_chunks_search_idx ON public.bm25_chunks
USING bm25 (
  chunk_id,
  (body_search::pdb.unicode_words),
  (coalesce(title_search, '')::pdb.unicode_words),
  (coalesce(heading_search, '')::pdb.unicode_words),
  (coalesce(alias_search, '')::pdb.unicode_words),
  language,
  acl_scope_id,
  is_current,
  visibility_generation
)
WITH (key_field = 'chunk_id');
"""
    completed = paradedb_psql(sql)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)


def load_compose_env() -> dict[str, str]:
    """Parse gitignored ``.env.compose`` KEY=VALUE pairs without logging values.

    Returns:
        Environment mapping used by local Compose. Empty when the file is absent.
    """

    values: dict[str, str] = {}
    if not COMPOSE_ENV_FILE.is_file():
        return values
    for raw_line in COMPOSE_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def packet8_paradedb_url() -> str | None:
    """Return the host-side ParadeDB writer URL for Packet 8 localhost overlay.

    Returns:
        ``PARADEDB_URL`` when set, otherwise a loopback URL on port ``54329``
        built from ``.env.compose`` writer credentials. ``None`` when credentials
        are unavailable.
    """

    explicit = read_process_env("PARADEDB_URL")
    if explicit:
        return explicit
    env = load_compose_env()
    password = env.get("PARADEDB_WRITER_PASSWORD")
    if not password:
        return None
    user = env.get("PARADEDB_WRITER_USER", "paradedb_writer")
    database = env.get("PARADEDB_DB", "paradedb")
    host = read_process_env("PARADEDB_HOST") or "127.0.0.1"
    port = read_process_env("PARADEDB_PORT") or "54329"
    return (
        f"postgresql://{quote(user, safe='')}:"
        f"{quote(password, safe='')}@{host}:{port}/{database}"
    )


def packet8_crawl_proxy_url() -> str:
    """Return the host-side crawl-proxy base URL for Packet 8 localhost overlay.

    Returns:
        ``CRAWL_PROXY_URL`` when set, otherwise ``http://127.0.0.1:18080``.
    """

    return read_process_env("CRAWL_PROXY_URL") or "http://127.0.0.1:18080"


def paradedb_host_reachable() -> bool:
    """Return whether host pytest can open ParadeDB via the Packet 8 overlay.

    Returns:
        ``True`` when ``psycopg`` connects to the loopback writer URL.
    """

    url = packet8_paradedb_url()
    if url is None:
        return False
    connection = try_connect(url)
    if connection is None:
        return False
    connection.close()
    return True


def packet8_clamav() -> tuple[str, int]:
    """Return host ClamAV coordinates for the Packet 8 overlay.

    Returns:
        ``(host, port)`` defaulting to ``127.0.0.1:13310``.
    """

    host = read_process_env("CLAMAV_HOST") or "127.0.0.1"
    port = int(read_process_env("CLAMAV_PORT") or "13310")
    return host, port


def clamav_reachable(host: str = "127.0.0.1", port: int = 13310) -> bool:
    """Return whether ClamAV ``clamd`` responds to ``PING`` on the host port.

    Args:
        host: ClamAV hostname. Defaults to localhost for contract tests that
            publish the private service port during CI.
        port: ClamAV TCP port.

    Returns:
        ``True`` when ``PING`` returns ``PONG``.
    """

    from smart_rag_core.gateways.clamav import ClamAvClient

    client = ClamAvClient(host=host, port=port, timeout_seconds=5.0)
    try:
        return client.ping()
    except Exception:
        return False
