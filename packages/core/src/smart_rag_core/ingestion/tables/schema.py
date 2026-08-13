"""Explicit Arrow schema for typed table artifacts."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from smart_rag_core.ingestion.tables.limits import (
    TABLE_ARTIFACT_SCHEMA_VERSION,
    TIMESTAMP_TIMEZONE,
    TIMESTAMP_UNIT,
)

PROVENANCE_COLUMN = "__provenance_json"
ROW_INDEX_COLUMN = "__row_index"


def base_provenance_fields() -> list[pa.Field]:
    """Return shared provenance columns appended to every table artifact."""

    return [
        pa.field(ROW_INDEX_COLUMN, pa.int64(), nullable=False),
        pa.field(PROVENANCE_COLUMN, pa.string(), nullable=False),
    ]


def schema_version_field() -> pa.Field:
    """Return the schema version metadata column."""

    return pa.field("__schema_version", pa.string(), nullable=False)


def infer_arrow_type(metadata: dict[str, Any]) -> pa.DataType:
    """Map parser cell metadata to an Arrow type without lossy coercion.

    Args:
        metadata: Parser-emitted cell metadata.

    Returns:
        Arrow data type preserving decimals, dates, and nullability intent.
    """

    typed_kind = metadata.get("typed_value_kind")
    if typed_kind == "integer":
        return pa.int64()
    if typed_kind == "float":
        return pa.float64()
    if typed_kind == "boolean":
        return pa.bool_()
    if typed_kind == "decimal":
        precision = int(metadata.get("decimal_precision", 38))
        scale = int(metadata.get("decimal_scale", 10))
        return pa.decimal128(min(precision, 38), scale)
    if typed_kind == "date":
        return pa.date32()
    if typed_kind == "timestamp":
        return pa.timestamp(TIMESTAMP_UNIT, tz=TIMESTAMP_TIMEZONE)
    return pa.string()


def build_table_schema(
    columns: list[tuple[str, pa.DataType]],
) -> pa.Schema:
    """Build one artifact schema with provenance columns.

    Args:
        columns: Ordered user-facing column name/type pairs.

    Returns:
        Explicit Arrow schema including provenance metadata columns.
    """

    fields = [pa.field(name, dtype, nullable=True) for name, dtype in columns]
    fields.extend(base_provenance_fields())
    fields.append(schema_version_field())
    metadata = {b"schema_version": TABLE_ARTIFACT_SCHEMA_VERSION.encode("utf-8")}
    return pa.schema(fields, metadata=metadata)
