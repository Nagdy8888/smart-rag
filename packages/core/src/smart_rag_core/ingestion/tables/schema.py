"""Explicit Arrow schema for typed table artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from smart_rag_core.ingestion.tables import arrow_facade as arrow
from smart_rag_core.ingestion.tables.limits import (
    TABLE_ARTIFACT_SCHEMA_VERSION,
    TIMESTAMP_TIMEZONE,
    TIMESTAMP_UNIT,
)

PROVENANCE_COLUMN = "__provenance_json"
ROW_INDEX_COLUMN = "__row_index"


def base_provenance_fields() -> list[arrow.ArrowField]:
    """Return shared provenance columns appended to every table artifact."""

    return [
        arrow.field(ROW_INDEX_COLUMN, arrow.int64(), nullable=False),
        arrow.field(PROVENANCE_COLUMN, arrow.string(), nullable=False),
    ]


def schema_version_field() -> arrow.ArrowField:
    """Return the schema version metadata column."""

    return arrow.field("__schema_version", arrow.string(), nullable=False)


def infer_arrow_type(metadata: dict[str, Any]) -> arrow.ArrowType:
    """Map parser cell metadata to an Arrow type without lossy coercion.

    Args:
        metadata: Parser-emitted cell metadata.

    Returns:
        Arrow data type preserving decimals, dates, and nullability intent.
    """

    typed_kind = metadata.get("typed_value_kind")
    if typed_kind == "integer":
        return arrow.int64()
    if typed_kind == "float":
        return arrow.float64()
    if typed_kind == "boolean":
        return arrow.bool_()
    if typed_kind == "decimal":
        precision = int(metadata.get("decimal_precision", 38))
        scale = int(metadata.get("decimal_scale", 10))
        return arrow.decimal128(min(precision, 38), scale)
    if typed_kind == "date":
        return arrow.date32()
    if typed_kind == "timestamp":
        return arrow.timestamp(TIMESTAMP_UNIT, tz=TIMESTAMP_TIMEZONE)
    return arrow.string()


def build_table_schema(
    columns: Sequence[tuple[str, arrow.ArrowType]],
) -> arrow.ArrowSchema:
    """Build one artifact schema with provenance columns.

    Args:
        columns: Ordered user-facing column name/type pairs.

    Returns:
        Explicit Arrow schema including provenance metadata columns.
    """

    fields: list[arrow.ArrowField] = [
        arrow.field(name, dtype, nullable=True) for name, dtype in columns
    ]
    fields.extend(base_provenance_fields())
    fields.append(schema_version_field())
    metadata = {b"schema_version": TABLE_ARTIFACT_SCHEMA_VERSION.encode("utf-8")}
    return arrow.schema(fields, metadata=metadata)
