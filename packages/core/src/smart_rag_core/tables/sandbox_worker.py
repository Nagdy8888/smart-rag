"""Isolated DuckDB worker. No secrets, no network config, one artifact path."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from smart_rag_core.tables.limits import (
    ALLOWED_TABLE,
    TABLE_MAX_OUTPUT_BYTES,
    TABLE_MAX_OUTPUT_ROWS,
    TABLE_MAX_TEMP_DIRECTORY_SIZE,
    TABLE_MEMORY_LIMIT,
    TABLE_STATEMENT_DEADLINE_SECONDS,
    TABLE_THREADS,
    TIMEZONE,
)

DUCKDB_CONNECT_CONFIG = {
    "enable_external_access": "false",
    "autoinstall_known_extensions": "false",
    "autoload_known_extensions": "false",
    "allow_unsigned_extensions": "false",
    "allow_community_extensions": "false",
    "threads": str(TABLE_THREADS),
    "memory_limit": TABLE_MEMORY_LIMIT,
    "max_temp_directory_size": TABLE_MAX_TEMP_DIRECTORY_SIZE,
}

_BLOCKED_SQL = re.compile(
    r"\b(?:attach|copy|install|load|pragma|create|drop|insert|update|"
    r"delete|alter)\b|://|\.\./",
    re.IGNORECASE,
)


class SandboxWorkerError(RuntimeError):
    """Worker-side sandbox failure."""


def run_worker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one compiled SELECT against the exact authorized Parquet.

    Args:
        payload: Trusted JSON from the parent executor. Must include
            ``parquet_path``, ``expected_path``, ``expected_sha256``,
            ``sql``, ``params``, ``count_sql``, ``count_params``,
            ``row_limit``, and ``output_byte_limit``.

    Returns:
        JSON-safe result with rows, input count, and provenance payloads.

    Raises:
        SandboxWorkerError: Path mismatch, blocked SQL, non-finite values,
            or DuckDB configuration/query failure.
    """

    import duckdb

    _apply_os_limits()
    parquet_path = Path(str(payload["parquet_path"])).resolve()
    expected = Path(str(payload["expected_path"])).resolve()
    if parquet_path != expected or not parquet_path.is_file():
        raise SandboxWorkerError("artifact_path_mismatch")
    expected_sha = str(payload.get("expected_sha256") or "")
    digest = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    if not expected_sha or digest != expected_sha:
        raise SandboxWorkerError("artifact_hash_mismatch")
    sql = str(payload["sql"])
    count_sql = str(payload["count_sql"])
    provenance_sql = str(payload.get("provenance_sql") or "")
    _reject_blocked(sql)
    _reject_blocked(count_sql)
    if provenance_sql:
        _reject_blocked(provenance_sql)
    row_limit = min(
        int(payload.get("row_limit", TABLE_MAX_OUTPUT_ROWS)),
        TABLE_MAX_OUTPUT_ROWS,
    )
    byte_limit = min(
        int(payload.get("output_byte_limit", TABLE_MAX_OUTPUT_BYTES)),
        TABLE_MAX_OUTPUT_BYTES,
    )
    duck = cast(Any, duckdb)
    connection = duck.connect(
        database=":memory:",
        read_only=False,
        config=DUCKDB_CONNECT_CONFIG,
    )
    try:
        connection.execute(f"SET TimeZone='{TIMEZONE}'")
        import pyarrow.parquet as pq

        arrow = cast(Any, pq).read_table(parquet_path)
        connection.register(ALLOWED_TABLE, arrow)
        connection.execute("SET lock_configuration=true")
        try:
            connection.execute("SET enable_external_access=true")
            raise SandboxWorkerError("lock_configuration_failed")
        except Exception as exc:
            if isinstance(exc, SandboxWorkerError):
                raise
        count_raw: object = connection.execute(
            count_sql, list(payload.get("count_params") or [])
        ).fetchone()
        input_count = 0
        if isinstance(count_raw, tuple) and count_raw and count_raw[0] is not None:
            first = cast(object, count_raw[0])
            input_count = int(str(first))
        source_payloads: list[str] = []
        if provenance_sql:
            prov_rows = connection.execute(
                provenance_sql, list(payload.get("provenance_params") or [])
            ).fetchmany(TABLE_MAX_OUTPUT_ROWS)
            source_payloads = [
                str(row[0]) for row in prov_rows if row and row[0] is not None
            ]
        relation = connection.execute(sql, list(payload.get("params") or []))
        description = relation.description
        columns = tuple(item[0] for item in description) if description else ()
        raw_rows = relation.fetchmany(row_limit + 1)
        if len(raw_rows) > row_limit:
            raise SandboxWorkerError("output_row_limit")
        rows = tuple(_json_row(columns, raw) for raw in raw_rows)
        encoded = json.dumps(rows, default=str).encode("utf-8")
        if len(encoded) > byte_limit:
            raise SandboxWorkerError("output_byte_limit")
        return {
            "ok": True,
            "input_row_count": input_count,
            "rows": list(rows),
            "columns": list(columns),
            "source_payloads": source_payloads,
            "timezone": TIMEZONE,
        }
    finally:
        connection.close()


def _apply_os_limits() -> None:
    """Apply POSIX address-space and CPU limits when available.

    Windows has no ``resource.setrlimit``. DuckDB ``memory_limit`` plus the
    parent process deadline remain the Windows bounds. Address space is 512
    MiB so CPython plus Arrow plus DuckDB can import; DuckDB's own cap stays
    64MB.
    """

    try:
        import resource
    except ImportError:
        return
    posix = cast(Any, resource)
    address_bytes = 512 * 1024 * 1024
    posix.setrlimit(posix.RLIMIT_AS, (address_bytes, address_bytes))
    cpu = int(TABLE_STATEMENT_DEADLINE_SECONDS) + 1
    posix.setrlimit(posix.RLIMIT_CPU, (cpu, cpu))


def _reject_blocked(sql: str) -> None:
    """Reject non-SELECT or mutating SQL inside the worker.

    Args:
        sql: Compiled SQL.

    Raises:
        SandboxWorkerError: Blocked construct.
    """

    lowered = sql.casefold().strip()
    if ";" in lowered or _BLOCKED_SQL.search(sql):
        raise SandboxWorkerError("blocked_sql")
    if not lowered.startswith("select "):
        raise SandboxWorkerError("only_select_permitted")


def _json_row(columns: tuple[str, ...], raw: tuple[object, ...]) -> dict[str, Any]:
    """Convert one DuckDB row to JSON-safe values.

    Args:
        columns: Column names.
        raw: Positional values.

    Returns:
        Dictionary of JSON-safe values.

    Raises:
        SandboxWorkerError: Non-finite numeric result.
    """

    row: dict[str, Any] = {}
    for name, value in zip(columns, raw, strict=True):
        row[name] = _json_value(value)
    return row


def _json_value(value: object) -> object:
    """Normalize one cell for JSON.

    Args:
        value: DuckDB cell.

    Returns:
        JSON-safe value.

    Raises:
        SandboxWorkerError: Infinity or NaN.
    """

    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SandboxWorkerError("non_finite_result")
        return value
    if isinstance(value, (int, str, bool)):
        return value
    return str(value)


def main() -> int:
    """Read one JSON payload from stdin and write one JSON result.

    Returns:
        Process exit code.
    """

    payload = json.loads(sys.stdin.read())
    try:
        result = run_worker_payload(payload)
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
