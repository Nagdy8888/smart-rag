"""Parquet serialization and round-trip helpers."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from typing import Any

from smart_rag_core.ingestion.tables import arrow_facade as arrow
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
    columns: Sequence[tuple[str, arrow.ArrowType]],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[bytes, arrow.ArrowSchema]:
    """Write one typed Parquet artifact in memory.

    Args:
        columns: Ordered logical column definitions.
        rows: Row dictionaries including provenance fields.

    Returns:
        Parquet bytes and the explicit schema used for the write.
    """

    schema = build_table_schema(columns)
    arrays: dict[str, arrow.ArrowArray] = {}
    for name, dtype in columns:
        arrays[name] = arrow.array([row.get(name) for row in rows], dtype=dtype)
    arrays[ROW_INDEX_COLUMN] = arrow.array(
        [int(row[ROW_INDEX_COLUMN]) for row in rows], dtype=arrow.int64()
    )
    arrays[PROVENANCE_COLUMN] = arrow.array(
        [str(row[PROVENANCE_COLUMN]) for row in rows], dtype=arrow.string()
    )
    arrays["__schema_version"] = arrow.array(
        [TABLE_ARTIFACT_SCHEMA_VERSION for _ in rows], dtype=arrow.string()
    )
    table = arrow.table(arrays, schema=schema)
    buffer = io.BytesIO()
    arrow.write_table(
        table,
        buffer,
        compression=TABLE_ARTIFACT_COMPRESSION,
        use_dictionary=TABLE_ARTIFACT_USE_DICTIONARY,
        write_statistics=TABLE_ARTIFACT_WRITE_STATISTICS,
        row_group_size=TABLE_ARTIFACT_ROW_GROUP_SIZE,
    )
    return buffer.getvalue(), schema


def read_parquet_artifact(data: bytes) -> arrow.ArrowTable:
    """Read one Parquet artifact without schema coercion.

    Args:
        data: Exact Parquet bytes.

    Returns:
        Arrow table preserving stored types.
    """

    return arrow.read_table(data)


def parquet_content_hash(data: bytes) -> str:
    """Return lowercase SHA-256 digest for one artifact payload."""

    return hashlib.sha256(data).hexdigest()


def provenance_json(payload: Mapping[str, Any]) -> str:
    """Serialize one row provenance dictionary canonically."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
