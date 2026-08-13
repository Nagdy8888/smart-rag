"""Build typed table artifacts from spreadsheet parser elements."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import pyarrow as pa

from smart_rag_core.ingestion.parser.types import (
    CsvLocator,
    ElementKind,
    ParseResult,
    XlsxLocator,
)
from smart_rag_core.ingestion.provenance import locator_to_dict
from smart_rag_core.ingestion.tables.bundle import TableArtifactBundle
from smart_rag_core.ingestion.tables.limits import (
    TABLE_ARTIFACT_SCHEMA_VERSION,
)
from smart_rag_core.ingestion.tables.manifest import (
    ColumnManifest,
    TableArtifactManifest,
)
from smart_rag_core.ingestion.tables.parquet_io import (
    parquet_content_hash,
    provenance_json,
    write_parquet_artifact,
)
from smart_rag_core.ingestion.tables.schema import (
    PROVENANCE_COLUMN,
    ROW_INDEX_COLUMN,
    infer_arrow_type,
)
from smart_rag_core.ingestion.tables.storage import table_artifact_storage_path

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def build_table_artifacts(
    parse_result: ParseResult,
    *,
    document_id: UUID,
    version_id: UUID,
) -> tuple[TableArtifactBundle, ...]:
    """Materialize typed Parquet artifacts for spreadsheet parse results.

    Args:
        parse_result: Closed parser output with table cell elements.
        document_id: Canonical document identifier.
        version_id: Immutable version identifier.

    Returns:
        Tuple of in-memory table artifact bundles with manifests.
    """

    if parse_result.format not in {"csv", "xlsx"}:
        return ()

    grouped = _group_rows(parse_result)
    bundles: list[TableArtifactBundle] = []
    headers = _collect_headers(parse_result)
    for sheet_name, rows in grouped.items():
        if not rows:
            continue
        columns = _column_manifest(rows, headers=headers.get(sheet_name, {}))
        arrow_columns = [
            (column.column_name, _arrow_type_for_column(rows, column)) for column in columns
        ]
        parquet_rows: list[dict[str, Any]] = []
        for row_index, row_cells in enumerate(rows):
            row_payload: dict[str, Any] = {
                ROW_INDEX_COLUMN: row_index,
                PROVENANCE_COLUMN: provenance_json(
                    {
                        "cells": [locator_to_dict(cell.locator) for cell in row_cells.values()],
                        "element_ids": [cell.element_id for cell in row_cells.values()],
                    }
                ),
                "__schema_version": TABLE_ARTIFACT_SCHEMA_VERSION,
            }
            for column in columns:
                cell = row_cells.get(column.header_ordinal)
                row_payload[column.column_name] = _coerce_value(
                    _typed_value(cell),
                    _arrow_type_for_column(rows, column),
                )
            parquet_rows.append(row_payload)
        parquet_bytes, _schema = write_parquet_artifact(columns=arrow_columns, rows=parquet_rows)
        safe_sheet = _safe_name(sheet_name or "sheet")
        storage_path = table_artifact_storage_path(
            document_id=document_id,
            version_id=version_id,
            sheet_name=safe_sheet,
            filename=f"{safe_sheet}.parquet",
        )
        manifest = TableArtifactManifest(
            table_name=safe_sheet,
            sheet_name=sheet_name,
            row_count=len(parquet_rows),
            column_count=len(columns),
            columns=tuple(columns),
            parquet_path=storage_path,
            content_hash_sha256=parquet_content_hash(parquet_bytes),
            byte_size=len(parquet_bytes),
            parser_version=parse_result.parser_version,
            cleaning_version=parse_result.cleaning_version,
            source_format=parse_result.format,
            provenance={"document_id": str(document_id), "version_id": str(version_id)},
        )
        bundles.append(
            TableArtifactBundle(
                manifest=manifest,
                parquet_bytes=parquet_bytes,
            )
        )
    return tuple(bundles)


def _collect_headers(parse_result: ParseResult) -> dict[str | None, dict[int, str]]:
    """Collect header text keyed by sheet and column ordinal."""

    headers: dict[str | None, dict[int, str]] = {}
    for element in parse_result.elements:
        if element.kind is not ElementKind.TABLE_HEADER:
            continue
        sheet = _sheet_name(element.locator)
        headers.setdefault(sheet, {})[_column_index(element.locator)] = element.text or ""
    return headers


def _group_rows(parse_result: ParseResult) -> dict[str | None, list[dict[int, Any]]]:
    """Group table cells by sheet and row index."""

    grouped: dict[str | None, dict[int, dict[int, Any]]] = {}
    for element in parse_result.elements:
        if element.kind is not ElementKind.TABLE_CELL:
            continue
        sheet = _sheet_name(element.locator)
        row_index = _row_index(element.locator)
        col_index = _column_index(element.locator)
        grouped.setdefault(sheet, {}).setdefault(row_index, {})[col_index] = element
    normalized: dict[str | None, list[dict[int, Any]]] = {}
    for sheet, rows in grouped.items():
        ordered_rows: list[dict[int, Any]] = []
        for row_index in sorted(rows):
            if row_index == 0 and parse_result.format == "csv":
                continue
            ordered_rows.append(rows[row_index])
        normalized[sheet] = ordered_rows
    return normalized


def _column_manifest(
    rows: list[dict[int, Any]],
    *,
    headers: dict[int, str],
) -> list[ColumnManifest]:
    """Infer logical columns with unique names and original header preservation."""

    if not rows:
        return []
    ordinals = sorted({ordinal for row in rows for ordinal in row})
    manifests: list[ColumnManifest] = []
    used_names: dict[str, int] = {}
    for ordinal in ordinals:
        header = headers.get(ordinal) or _header_text(_first_cell(rows, ordinal))
        base_name = _safe_name(header or f"col_{ordinal}")
        count = used_names.get(base_name, 0)
        used_names[base_name] = count + 1
        column_name = base_name if count == 0 else f"{base_name}_{count + 1}"
        first_cell = _first_cell(rows, ordinal)
        hidden = bool(first_cell and getattr(first_cell.locator, "hidden_sheet", False))
        manifests.append(
            ColumnManifest(
                column_name=column_name,
                original_header=header or f"col_{ordinal}",
                header_ordinal=ordinal,
                column_type=_column_type_name(rows, ordinal),
                hidden=hidden,
            )
        )
    return manifests


def _first_cell(rows: list[dict[int, Any]], ordinal: int) -> Any:
    """Return the first non-null cell for one column ordinal."""

    for row in rows:
        cell = row.get(ordinal)
        if cell is not None:
            return cell
    return None


def _column_type_name(rows: list[dict[int, Any]], ordinal: int) -> str:
    """Infer a logical column type name from all cells in the column."""

    kinds: set[str] = set()
    has_formula = False
    for row in rows:
        cell = row.get(ordinal)
        if cell is None:
            continue
        if cell.metadata.get("formula_text"):
            has_formula = True
        kinds.add(str(cell.metadata.get("typed_value_kind", "string")))
    if has_formula or len(kinds) > 1:
        return "string"
    return next(iter(kinds)) if kinds else "string"


def _arrow_type_for_column(rows: list[dict[int, Any]], column: ColumnManifest) -> pa.DataType:
    """Resolve Arrow type for one column without lossy mixed-type coercion."""

    if column.column_type == "string":
        return pa.string()
    sample = _first_cell(rows, column.header_ordinal)
    metadata = dict(sample.metadata) if sample is not None else {"typed_value_kind": column.column_type}
    return infer_arrow_type(metadata)


def _coerce_value(value: Any, arrow_type: pa.DataType) -> Any:
    """Coerce one Python value to the declared Arrow type safely."""

    if value is None:
        return None
    if pa.types.is_string(arrow_type):
        return str(value)
    if pa.types.is_int64(arrow_type) and not isinstance(value, bool):
        return int(value)
    if pa.types.is_floating(arrow_type):
        return float(value)
    if pa.types.is_boolean(arrow_type):
        return bool(value) if isinstance(value, bool) else str(value).lower() == "true"
    return value


def _typed_value(cell: Any) -> Any:
    """Return typed cell value without recalculating formulas."""

    if cell is None:
        return None
    metadata = cell.metadata
    if metadata.get("formula_text"):
        return metadata["formula_text"]
    kind = metadata.get("typed_value_kind")
    text = cell.text
    if kind == "integer" and text is not None:
        return int(text)
    if kind == "float" and text is not None:
        return float(text)
    if kind == "boolean" and text is not None:
        return text.lower() == "true"
    return text


def _sheet_name(locator: Any) -> str | None:
    """Extract sheet name from spreadsheet locators."""

    if isinstance(locator, XlsxLocator):
        return locator.sheet_name
    if isinstance(locator, CsvLocator):
        return "csv"
    return None


def _row_index(locator: Any) -> int:
    """Extract row index from spreadsheet locators."""

    if isinstance(locator, XlsxLocator):
        return locator.row
    if isinstance(locator, CsvLocator):
        return locator.record_index
    return 0


def _column_index(locator: Any) -> int:
    """Extract column index from spreadsheet locators."""

    if isinstance(locator, XlsxLocator):
        return locator.col - 1
    if isinstance(locator, CsvLocator):
        return locator.column_index
    return 0


def _header_text(cell: Any) -> str:
    """Resolve original header text for one cell."""

    locator = cell.locator
    header = getattr(locator, "header_text", None)
    return str(header or "")


def _safe_name(value: str) -> str:
    """Sanitize sheet/table names for Storage paths."""

    cleaned = _SAFE_NAME_RE.sub("_", value.strip())
    return cleaned or "sheet"
