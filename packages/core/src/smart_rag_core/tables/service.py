"""Deterministic structured_table_query entrypoint."""

from __future__ import annotations

import json
import math
from typing import cast

from smart_rag_core.ingestion.tables.limits import TABLE_ARTIFACT_SCHEMA_VERSION
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.tables.builder import compile_table_query
from smart_rag_core.tables.executor import execute_compiled_query
from smart_rag_core.tables.plan import TableQueryPlan
from smart_rag_core.tables.refusals import TableQueryRefusal, refuse_if_invalid
from smart_rag_core.tables.resolver import TableArtifactResolver, TableResolveError
from smart_rag_core.tables.types import AuthorizedTable, TableQueryResult

_CALCULATION_HINTS = frozenset(
    {
        "filter",
        "sort",
        "group",
        "sum",
        "count",
        "average",
        "min",
        "max",
        "comparison",
    }
)


class StructuredTableError(RuntimeError):
    """Structured-table execution failed closed."""


def should_bind_structured_table(
    *, table_intent: bool, operation_hints: tuple[str, ...]
) -> bool:
    """Return whether Hybrid should bind the structured-table path.

    Ordinary cell/text lookup stays Hybrid. Catalog discovery is never used.

    Args:
        table_intent: Query-profile table flag.
        operation_hints: Profile operation hints.

    Returns:
        True when a calculation operation is requested.
    """

    if not table_intent:
        return False
    return bool(
        _CALCULATION_HINTS.intersection(hint.casefold() for hint in operation_hints)
    )


def structured_table_query(
    plan: TableQueryPlan,
    *,
    caller: CallerContext,
    resolver: TableArtifactResolver,
) -> TableQueryResult:
    """Execute one authorized TableQueryPlan.

    Args:
        plan: Validated declarative plan. Extra fields are forbidden.
        caller: Server-derived caller. Never a client-selected path.
        resolver: Authoritative table resolver.

    Returns:
        Deterministic values plus provenance.

    Raises:
        TableQueryRefusal: Clarification/refusal before execution.
        TableResolveError: Unauthorized, stale, or deleted table.
        StructuredTableError: Sandbox failure or post-recheck loss.
        TableSandboxError: Deadline or worker failure.
    """

    table = resolver.resolve(
        table_id=plan.table_id, version_id=plan.version_id, caller=caller
    )
    if table.version_id != plan.version_id:
        raise TableResolveError("wrong_current_version")
    refuse_if_invalid(plan, table)
    allowed = frozenset(column.column_name for column in table.columns)
    compiled = compile_table_query(plan, allowed_columns=allowed)
    raw = execute_compiled_query(
        compiled,
        parquet_path=table.local_parquet_path,
        expected_sha256=table.parquet_sha256,
        row_limit=plan.row_limit,
        output_byte_limit=plan.output_byte_limit,
    )
    if not resolver.recheck(
        table_id=plan.table_id, version_id=plan.version_id, caller=caller
    ):
        raise StructuredTableError("authorization_lost_after_query")
    rows = tuple(dict(item) for item in raw["rows"])
    units = plan.units
    if units is None:
        units = next(
            (
                column.unit or column.currency
                for column in table.columns
                if column.unit or column.currency
            ),
            None,
        )
    payloads = tuple(str(item) for item in raw.get("source_payloads") or ())
    source_ranges = _source_ranges(table, payloads)
    if not source_ranges:
        raise TableQueryRefusal("missing_cell_provenance")
    diagnostics = ("timezone:UTC", "rounding:decimal-as-text")
    return TableQueryResult(
        table_id=table.table_id,
        version_id=table.version_id,
        document_id=table.document_id,
        artifact_sha256=table.parquet_sha256,
        schema_version=TABLE_ARTIFACT_SCHEMA_VERSION,
        workbook=table.workbook_name,
        sheet=table.sheet_name,
        source_ranges=source_ranges,
        operation=_operation_label(plan),
        predicates=tuple(
            f"{item.column}:{item.operator.value}" for item in plan.predicates
        ),
        grouping=plan.group_by,
        units=units,
        rows=rows,
        input_row_count=int(raw["input_row_count"]),
        output_row_count=len(rows),
        null_policy="skip",
        rounding="decimal-as-text",
        diagnostics=diagnostics,
    )


def _source_ranges(
    table: AuthorizedTable, payloads: tuple[str, ...]
) -> tuple[str, ...]:
    """Extract exact workbook/sheet/cell ranges from row provenance.

    Args:
        table: Authorized table.
        payloads: Distinct ``__provenance_json`` strings from matching rows.

    Returns:
        Deduplicated range descriptors in first-seen order.
    """

    workbook = table.workbook_name or table.table_name
    sheet = table.sheet_name
    found: list[str] = []
    seen: set[str] = set()
    for raw in payloads:
        for label in source_range_labels(raw, workbook=workbook, sheet=sheet):
            if label not in seen:
                seen.add(label)
                found.append(label)
    return tuple(found)


def source_range_labels(
    raw: str, *, workbook: str, sheet: str | None
) -> tuple[str, ...]:
    """Parse one provenance JSON blob into range labels.

    Args:
        raw: Provenance JSON.
        workbook: Workbook or CSV name.
        sheet: Sheet name fallback.

    Returns:
        Zero or more labels. Empty when the blob is not usable provenance.
    """

    try:
        loaded: object = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(loaded, dict):
        return ()
    untyped = cast(dict[object, object], loaded)
    data: dict[str, object] = {str(key): value for key, value in untyped.items()}
    labels: list[str] = []
    cells = data.get("cells")
    if isinstance(cells, list):
        for cell_obj in cast(list[object], cells):
            if not isinstance(cell_obj, dict):
                continue
            cell_untyped = cast(dict[object, object], cell_obj)
            cell: dict[str, object] = {
                str(key): value for key, value in cell_untyped.items()
            }
            if cell.get("format") == "pdf":
                page = cell.get("page_index")
                coordinates = [
                    cell.get(key)
                    for key in ("bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1")
                ]
                if (
                    isinstance(page, int)
                    and not isinstance(page, bool)
                    and page >= 0
                    and all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                        for value in coordinates
                    )
                ):
                    x0, y0, x1, y1 = (
                        float(cast(int | float, value)) for value in coordinates
                    )
                    if 0 <= x0 < x1 and 0 <= y0 < y1:
                        labels.append(
                            f"{workbook}!Physical PDF page {page + 1}!bbox({x0!r},{y0!r},{x1!r},{y1!r})"
                        )
                continue
            sheet_name = str(cell.get("sheet_name") or sheet or "")
            cell_ref_obj = cell.get("range_ref") or cell.get("cell_ref")
            cell_ref = "" if cell_ref_obj is None else str(cell_ref_obj)
            if not cell_ref:
                record = cell.get("record_index")
                column = cell.get("column_index")
                if record is not None and column is not None:
                    cell_ref = f"R{record}C{column}"
            if not cell_ref:
                continue
            if sheet_name:
                labels.append(f"{workbook}!{sheet_name}!{cell_ref}")
            else:
                labels.append(f"{workbook}!{cell_ref}")
    simple_range = data.get("range")
    if isinstance(simple_range, str) and simple_range:
        sheet_name = str(data.get("sheet") or sheet or "")
        if sheet_name:
            labels.append(f"{workbook}!{sheet_name}!{simple_range}")
        else:
            labels.append(f"{workbook}!{simple_range}")
    return tuple(labels)


def _operation_label(plan: TableQueryPlan) -> str:
    """Summarize the executed operation.

    Args:
        plan: Validated plan.

    Returns:
        Stable operation label.
    """

    if plan.comparison is not None:
        return f"comparison:{plan.comparison.aggregation.value}"
    if plan.aggregations:
        return ",".join(item.op.value for item in plan.aggregations)
    if plan.group_by:
        return "group"
    if plan.order_by:
        return "sort"
    return "filter"
