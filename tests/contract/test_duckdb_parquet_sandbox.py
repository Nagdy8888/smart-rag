"""Contract tests for DuckDB read-only Parquet sandbox."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pyarrow as pa
import pytest
from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.tables import parquet_io
from smart_rag_core.ingestion.tables.duckdb_sandbox import (
    DuckdbSandbox,
    DuckdbSandboxError,
)
from smart_rag_core.ingestion.tables.schema import PROVENANCE_COLUMN, ROW_INDEX_COLUMN

from tests.fixtures.parser import build_csv_fixture

DOCUMENT_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
VERSION_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")


def _arrow_type(name: str) -> object:
    """Return one pyarrow dtype by name without relying on untyped stubs.

    Args:
        name: ``pyarrow`` factory attribute such as ``string``.

    Returns:
        The constructed dtype object.
    """

    factory: Callable[[], object] = getattr(pa, name)
    return factory()


def _write_parquet(
    *,
    columns: list[tuple[str, object]],
    rows: list[dict[str, object]],
) -> bytes:
    """Write Parquet bytes through the production helper with explicit types.

    Args:
        columns: Logical column name and dtype pairs.
        rows: Row dictionaries including provenance fields.

    Returns:
        In-memory Parquet payload.
    """

    writer: Callable[..., tuple[object, object]] = parquet_io.write_parquet_artifact
    payload, _schema = writer(columns=columns, rows=rows)
    return bytes(payload)


def test_duckdb_sandbox_allows_exact_fixture_read(tmp_path: Path) -> None:
    """Sandbox permits bounded SELECT over the exact fixture Parquet."""

    payload, digest = build_csv_fixture()
    path = tmp_path / "fixture.csv"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "csv")
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    parquet_path = tmp_path / "fixture.parquet"
    parquet_path.write_bytes(result.table_artifacts[0].parquet_bytes)
    sandbox = DuckdbSandbox(allowed_parquet=parquet_path)
    rows = sandbox.query_fixture(column="name", limit=5)
    assert rows


def test_duckdb_sandbox_blocks_path_traversal_and_mutations(tmp_path: Path) -> None:
    """Sandbox rejects traversal, URLs, ATTACH/COPY, and mutation attempts."""

    payload = _write_parquet(
        columns=[("name", _arrow_type("string"))],
        rows=[
            {
                "name": "x",
                ROW_INDEX_COLUMN: 0,
                PROVENANCE_COLUMN: "{}",
                "__schema_version": "table_parquet_v1",
            }
        ],
    )
    parquet_path = tmp_path / "allowed.parquet"
    parquet_path.write_bytes(payload)
    sandbox = DuckdbSandbox(allowed_parquet=parquet_path)
    blocked = [
        "ATTACH 'x.db' AS db",
        "COPY allowed_fixture TO '/tmp/out.parquet'",
        "INSTALL httpfs",
        "SELECT * FROM read_parquet('../secrets.parquet')",
        "INSERT INTO allowed_fixture VALUES (1)",
        "SELECT * FROM read_parquet('https://example.com/x.parquet')",
    ]
    for sql in blocked:
        with pytest.raises(DuckdbSandboxError):
            sandbox.assert_blocked(sql)
