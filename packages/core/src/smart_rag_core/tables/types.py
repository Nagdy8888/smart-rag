"""Authorized table artifacts and structured-table results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from smart_rag_core.ingestion.tables.manifest import ColumnManifest


@dataclass(frozen=True, slots=True)
class AuthorizedTable:
    """Server-resolved table artifact. Paths never come from the plan.

    Attributes:
        table_id: Canonical table UUID.
        document_id: Owning document.
        version_id: Current version.
        table_name: Artifact table name.
        sheet_name: Workbook sheet, if any.
        workbook_name: Source workbook or CSV name.
        columns: Manifest columns with internal ids.
        parquet_sha256: Content hash.
        local_parquet_path: Exact immutable local file after fetch.
        source_format: csv or xlsx.
        hidden_sheet: True when the sheet is hidden.
        formula_columns: Internal ids whose cells include formula text.
    """

    table_id: UUID
    document_id: UUID
    version_id: UUID
    table_name: str
    sheet_name: str | None
    workbook_name: str | None
    columns: tuple[ColumnManifest, ...]
    parquet_sha256: str
    local_parquet_path: Path
    source_format: str
    hidden_sheet: bool = False
    formula_columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledTableQuery:
    """Application-owned SQL plus bound parameters. Not user SQL.

    Attributes:
        sql: SELECT compiled from the plan.
        params: Positional parameters.
        count_sql: Input-row COUNT query.
        count_params: Parameters for ``count_sql``.
        provenance_sql: DISTINCT provenance JSON for matching rows.
        provenance_params: Parameters for ``provenance_sql``.
    """

    sql: str
    params: tuple[object, ...]
    count_sql: str
    count_params: tuple[object, ...]
    provenance_sql: str
    provenance_params: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class TableQueryResult:
    """Deterministic table values plus provenance. Not an answer.

    Attributes:
        table_id: Canonical table UUID.
        version_id: Current version.
        document_id: Owning document.
        artifact_sha256: Parquet hash.
        schema_version: ``table_parquet_v1``.
        workbook: Workbook or CSV name.
        sheet: Sheet name.
        source_ranges: Exact ranges or cell lists.
        operation: Aggregations and comparison summary.
        predicates: Machine-readable predicate list.
        grouping: Group-by columns.
        units: Result unit.
        rows: Result dictionaries with JSON-safe values.
        input_row_count: Rows matching predicates before aggregation.
        output_row_count: Returned rows.
        null_policy: ``skip`` for aggregations.
        rounding: Decimal rounding description.
        diagnostics: Refusal or sandbox notes.
    """

    table_id: UUID
    version_id: UUID
    document_id: UUID
    artifact_sha256: str
    schema_version: str
    workbook: str | None
    sheet: str | None
    source_ranges: tuple[str, ...]
    operation: str
    predicates: tuple[str, ...]
    grouping: tuple[str, ...]
    units: str | None
    rows: tuple[dict[str, Any], ...]
    input_row_count: int
    output_row_count: int
    null_policy: str
    rounding: str
    diagnostics: tuple[str, ...] = ()
