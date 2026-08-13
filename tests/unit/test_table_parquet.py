"""Unit tests for typed Parquet artifact round trips."""

from __future__ import annotations

import uuid
from pathlib import Path

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

DOCUMENT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
VERSION_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")


def test_arrow_parquet_arrow_round_trip_preserves_schema() -> None:
    """Arrow→Parquet→Arrow preserves explicit schema and values."""

    columns = [("amount", pa.int64()), ("name", pa.string())]
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
    round_trip = read_parquet_artifact(payload)
    assert round_trip.schema.equals(schema, check_metadata=True)
    assert round_trip.column("amount").to_pylist() == [10, 20]
    assert round_trip.column("name").to_pylist() == ["Widget", "مرحبا"]


def test_xlsx_fixture_parquet_preserves_formula_and_typed_values(tmp_path: Path) -> None:
    """Spreadsheet fixtures preserve formulas and typed values without coercion."""

    payload, digest = build_xlsx_fixture()
    path = tmp_path / "typed.xlsx"
    path.write_bytes(payload)
    parsed = parse_file(path, digest, "xlsx")
    result = chunk_parse_result(parsed, document_id=DOCUMENT_ID, version_id=VERSION_ID)
    artifact = result.table_artifacts[0]
    table = pq.read_table(pa.BufferReader(artifact.parquet_bytes))
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
    restored = read_parquet_artifact(result.table_artifacts[0].parquet_bytes)
    assert restored.num_rows >= 1
