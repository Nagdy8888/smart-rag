"""Process-isolated DuckDB executor with deadline, interrupt, and kill grace."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from smart_rag_core.settings import snapshot_process_environ
from smart_rag_core.tables.limits import (
    TABLE_KILL_GRACE_SECONDS,
    TABLE_STATEMENT_DEADLINE_SECONDS,
)
from smart_rag_core.tables.types import CompiledTableQuery

_SECRET_ENV_FRAGMENTS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "JWT",
    "OPENAI",
    "SUPABASE",
    "LANGSMITH",
    "DATABASE_URL",
    "POSTGRES",
)


class TableSandboxError(RuntimeError):
    """Sandbox process failed, timed out, or attempted escape."""


def stripped_worker_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment without application or provider secrets.

    Args:
        source: Base environment. Defaults to a settings process snapshot.

    Returns:
        Allow-listed process environment for the worker.
    """

    env = dict(source if source is not None else snapshot_process_environ())
    kept: dict[str, str] = {}
    allow = {
        "PATH",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "PATHEXT",
        "COMSPEC",
        "TZ",
        "HOME",
        "USERPROFILE",
        "TMP",
        "TEMP",
        "TMPDIR",
    }
    for key, value in env.items():
        upper = key.upper()
        if any(fragment in upper for fragment in _SECRET_ENV_FRAGMENTS):
            continue
        if upper in allow or upper.startswith("PYTHON"):
            kept[key] = value
    kept.setdefault("PYTHONIOENCODING", "utf-8")
    kept["SMART_RAG_TABLE_SANDBOX"] = "1"
    return kept


def execute_compiled_query(
    compiled: CompiledTableQuery,
    *,
    parquet_path: Path,
    expected_sha256: str,
    row_limit: int,
    output_byte_limit: int,
    deadline_seconds: float = TABLE_STATEMENT_DEADLINE_SECONDS,
    kill_grace_seconds: float = TABLE_KILL_GRACE_SECONDS,
) -> dict[str, Any]:
    """Run compiled SQL in a fresh no-secret subprocess.

    The process is never reused. Timeout sends terminate (interrupt), then
    kill after ``kill_grace_seconds``.

    Args:
        compiled: Application-owned SQL.
        parquet_path: Exact authorized local Parquet file.
        expected_sha256: Catalog content hash, not a hash of untrusted bytes.
        row_limit: Output row cap.
        output_byte_limit: Serialized output cap.
        deadline_seconds: Process wait timeout.
        kill_grace_seconds: Grace before kill.

    Returns:
        Worker JSON payload with ``ok``, ``rows``, and ``input_row_count``.

    Raises:
        TableSandboxError: Timeout, kill, non-zero exit, or worker error.
    """

    resolved = parquet_path.resolve()
    if not resolved.is_file():
        raise TableSandboxError("missing_parquet_artifact")
    if not expected_sha256:
        raise TableSandboxError("missing_catalog_hash")
    payload = {
        "parquet_path": resolved.as_posix(),
        "expected_path": resolved.as_posix(),
        "expected_sha256": expected_sha256,
        "sql": compiled.sql,
        "params": list(compiled.params),
        "count_sql": compiled.count_sql,
        "count_params": list(compiled.count_params),
        "provenance_sql": compiled.provenance_sql,
        "provenance_params": list(compiled.provenance_params),
        "row_limit": row_limit,
        "output_byte_limit": output_byte_limit,
    }
    command = [sys.executable, "-m", "smart_rag_core.tables.sandbox_worker"]
    process = subprocess.Popen(  # noqa: S603 - fixed module path, no user argv
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=stripped_worker_env(),
        text=True,
        cwd=str(resolved.parent),
    )
    try:
        stdout, stderr = process.communicate(
            json.dumps(payload), timeout=deadline_seconds
        )
    except subprocess.TimeoutExpired as exc:
        process.terminate()
        try:
            process.wait(timeout=kill_grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=kill_grace_seconds)
        raise TableSandboxError("statement_deadline") from exc
    if process.returncode != 0:
        raise TableSandboxError(stderr.strip() or stdout.strip() or "worker_failed")
    try:
        loaded: object = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise TableSandboxError("worker_output_invalid") from exc
    if not isinstance(loaded, dict):
        raise TableSandboxError("worker_output_invalid")
    untyped = cast(dict[object, object], loaded)
    result: dict[str, Any] = {str(key): value for key, value in untyped.items()}
    if not result.get("ok"):
        raise TableSandboxError(str(result.get("error") or "worker_failed"))
    return result
