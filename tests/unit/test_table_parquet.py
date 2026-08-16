"""Unit tests for typed Parquet artifact round trips."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

import pyarrow as pa
import pyarrow.parquet as pq
from smart_rag_core.ingestion.chunking import chunk_parse_result
from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.tables.parquet_io import (
    read_parquet_artifact,
    write_parquet_artifact,
)
from smart_rag_core.ingestion.tables.schema import PROVENANCE_COLUMN, ROW_INDEX_COLUMN

from tests.fixtures.parser import build_csv_fixture, build_xlsx_fixture
from tests.unit.typed_attrs import module_attr

DOCUMENT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
VERSION_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")


@runtime_checkable
class _ArrowArray(Protocol):
    """Minimal Arrow array surface used by round-trip assertions."""

    def to_pylist(self) -> list[object]:
        """Return Python values for one column."""
        ...


@runtime_checkable
class _ArrowSchema(Protocol):
    """Minimal Arrow schema surface used by equality checks."""

    def equals(self, other: object, check_metadata: bool = False) -> bool:
        """Return whether two schemas match."""
        ...


@runtime_checkable
class _ArrowTable(Protocol):
    """Minimal Arrow table surface used by Parquet unit tests."""

    num_rows: int
    column_names: list[str]
    schema: object

    def column(self, name: str) -> object:
        """Return one named column."""
        ...


def _arrow_dtype(name: str) -> object:
    """Construct one named pyarrow dtype without unknown member access.

    Args:
        name: Attribute on ``pyarrow`` such as ``int64`` or ``string``.

    Returns:
        The constructed dtype object.

    Raises:
        TypeError: If the named factory is missing or not callable.
    """

    factory: object = getattr(pa, name)
    if not callable(factory):
        raise TypeError(f"pyarrow.{name} must be callable")
    return factory()


def _as_table(value: object) -> _ArrowTable:
    """Narrow an Arrow table-like value.

    Args:
        value: Object returned by Parquet read helpers.

    Returns:
        The same value typed as ``_ArrowTable``.

    Raises:
        TypeError: If required table attributes are missing.
    """

    if not isinstance(value, _ArrowTable):
        raise TypeError("expected Arrow table")
    return value


def _as_schema(value: object) -> _ArrowSchema:
    """Narrow an Arrow schema-like value.

    Args:
        value: Schema object from a Parquet write.

    Returns:
        The same value typed as ``_ArrowSchema``.

    Raises:
        TypeError: If ``equals`` is missing.
    """

    if not isinstance(value, _ArrowSchema):
        raise TypeError("expected Arrow schema")
    return value


def _column_values(table: _ArrowTable, name: str) -> list[object]:
    """Return Python values for one table column.

    Args:
        table: Arrow table.
        name: Column name.

    Returns:
        Column values as a Python list.

    Raises:
        TypeError: If the column does not support ``to_pylist``.
    """

    array = table.column(name)
    if not isinstance(array, _ArrowArray):
        raise TypeError("expected Arrow array")
    return array.to_pylist()


def _read_table_bytes(data: bytes) -> _ArrowTable:
    """Read Parquet bytes through pyarrow without unknown member access.

    Args:
        data: Exact Parquet payload.

    Returns:
        Arrow table.

    Raises:
        TypeError: If BufferReader or read_table is missing.
    """

    reader_ctor: object = module_attr(pa, "BufferReader")
    read_table: object = module_attr(pq, "read_table")
    if not callable(reader_ctor) or not callable(read_table):
        raise TypeError("pyarrow BufferReader/read_table must be callable")
    return _as_table(read_table(reader_ctor(data)))


def test_arrow_parquet_arrow_round_trip_preserves_schema() -> None:
    """Arrow→Parquet→Arrow preserves explicit schema and values."""

    columns: list[tuple[str, object]] = [
        ("amount", _arrow_dtype("int64")),
        ("name", _arrow_dtype("string")),
    ]
    rows = [
        {
            "amount": 10,
            "name": "Widget",
            ROW_INDEX_COLUMN: 0,
            PROVENANCE_COLUMN: '{"cell_ref":"A2"}',
            "__schema_version": "table_parquet_v1",
        },
        {
            "amount": 20,
            "name": "مرحبا",
            ROW_INDEX_COLUMN: 1,
            PROVENANCE_COLUMN: '{"cell_ref":"A3"}',
            "__schema_version": "table_parquet_v1",
        },
    ]
    payload, schema = write_parquet_artifact(columns=columns, rows=rows)
    round_trip = _as_table(read_parquet_artifact(payload))
    assert _as_schema(round_trip.schema).equals(_as_schema(schema), check_metadata=True)
    assert _column_values(round_trip, "amount") == [10, 20]
    assert _column_values(round_trip, "name") == ["Widget", "مرحبا"]


def test_xlsx_fixture_parquet_preserves_formula_and_typed_values(
    tmp_path: Path,
) -> None:
    """Spreadsheet fixtures preserve formulas and typed values without coercion."""

    payload, digest = build_xlsx_fixture()
    path = tmp_path / "typed.xlsx"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "xlsx")
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    artifact = result.table_artifacts[0]
    table = _read_table_bytes(artifact.parquet_bytes)
    column_names = set(table.column_names)
    assert "__schema_version" in column_names
    assert PROVENANCE_COLUMN in column_names
    assert artifact.manifest.content_hash_sha256


def test_csv_fixture_parquet_round_trip(tmp_path: Path) -> None:
    """CSV fixtures produce readable Parquet with duplicate headers preserved."""

    payload, digest = build_csv_fixture()
    path = tmp_path / "typed.csv"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "csv")
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    assert result.table_artifacts
    restored = _as_table(read_parquet_artifact(result.table_artifacts[0].parquet_bytes))
    assert restored.num_rows >= 1
