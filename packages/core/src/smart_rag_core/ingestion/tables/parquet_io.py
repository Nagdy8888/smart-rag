"""Parquet serialization and round-trip helpers."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from smart_rag_core.ingestion.tables.limits import (
    TABLE_ARTIFACT_COMPRESSION,
    TABLE_ARTIFACT_ROW_GROUP_SIZE,
    TABLE_ARTIFACT_SCHEMA_VERSION,
    TABLE_ARTIFACT_USE_DICTIONARY,
    TABLE_ARTIFACT_WRITE_STATISTICS,
)
from smart_rag_core.ingestion.tables.schema import (
    PROVENANCE_COLUMN,
    ROW_INDEX_COLUMN,
    build_table_schema,
)


def write_parquet_artifact(
    *,
    columns: list[tuple[str, pa.DataType]],
    rows: list[dict[str, Any]],
) -> tuple[bytes, pa.Schema]:
    """Write one typed Parquet artifact in memory.

    Args:
        columns: Ordered logical column definitions.
        rows: Row dictionaries including provenance fields.

    Returns:
        Parquet bytes and the explicit schema used for the write.
    """

    schema = build_table_schema(columns)
    arrays: dict[str, pa.Array] = {}
    for name, dtype in columns:
        arrays[name] = pa.array([row.get(name) for row in rows], type=dtype)
    arrays[ROW_INDEX_COLUMN] = pa.array(
        [int(row[ROW_INDEX_COLUMN]) for row in rows], type=pa.int64()
    )
    arrays[PROVENANCE_COLUMN] = pa.array(
        [str(row[PROVENANCE_COLUMN]) for row in rows], type=pa.string()
    )
    arrays["__schema_version"] = pa.array(
        [TABLE_ARTIFACT_SCHEMA_VERSION for _ in rows], type=pa.string()
    )
    table = pa.table(arrays, schema=schema)
    buffer = io.BytesIO()
    pq.write_table(
        table,
        buffer,
        compression=TABLE_ARTIFACT_COMPRESSION,
        use_dictionary=TABLE_ARTIFACT_USE_DICTIONARY,
        write_statistics=TABLE_ARTIFACT_WRITE_STATISTICS,
        row_group_size=TABLE_ARTIFACT_ROW_GROUP_SIZE,
    )
    return buffer.getvalue(), schema


def read_parquet_artifact(data: bytes) -> pa.Table:
    """Read one Parquet artifact without schema coercion.

    Args:
        data: Exact Parquet bytes.

    Returns:
        Arrow table preserving stored types.
    """

    return pq.read_table(io.BytesIO(data))


def parquet_content_hash(data: bytes) -> str:
    """Return lowercase SHA-256 digest for one artifact payload."""

    return hashlib.sha256(data).hexdigest()


def provenance_json(payload: dict[str, Any]) -> str:
    """Serialize one row provenance dictionary canonically."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
