"""Refuse plans that would invent values or mix incompatible columns."""

from __future__ import annotations

from collections import Counter

from smart_rag_core.ingestion.tables.manifest import ColumnManifest
from smart_rag_core.tables.plan import TableAggregationOp, TableQueryPlan
from smart_rag_core.tables.types import AuthorizedTable


class TableQueryRefusal(ValueError):
    """Structured-table clarification or refusal. Not a calculation."""

    def __init__(self, code: str) -> None:
        """Store a machine-readable refusal code.

        Args:
            code: Stable refusal identifier.
        """

        super().__init__(code)
        self.code = code


def refuse_if_invalid(plan: TableQueryPlan, table: AuthorizedTable) -> None:
    """Raise a typed refusal before DuckDB runs.

    Args:
        plan: Validated plan.
        table: Authorized current artifact.

    Raises:
        TableQueryRefusal: Hidden sheet, duplicate header reference, mixed
            units/currency, formula/string aggregation, or unknown column.
    """

    by_id = {column.column_name: column for column in table.columns}
    if table.hidden_sheet or any(column.hidden for column in table.columns):
        raise TableQueryRefusal("hidden_sheet_policy")
    _reject_duplicate_header_reference(plan, table.columns)
    requested = _requested_columns(plan)
    for name in requested:
        if name not in by_id:
            raise TableQueryRefusal(f"unknown_column:{name}")
    _reject_formula_aggregation(plan, table, by_id)
    _reject_mixed_units(plan, by_id)


def _requested_columns(plan: TableQueryPlan) -> tuple[str, ...]:
    """Collect internal ids referenced by the plan.

    Args:
        plan: Validated plan.

    Returns:
        Unique column ids.
    """

    names = list(plan.columns) + list(plan.group_by)
    names.extend(item.column for item in plan.predicates)
    names.extend(item.column for item in plan.order_by)
    for item in plan.aggregations:
        if item.column is not None:
            names.append(item.column)
    if plan.comparison is not None:
        names.append(plan.comparison.column)
        names.extend(item.column for item in plan.comparison.left)
        names.extend(item.column for item in plan.comparison.right)
    return tuple(dict.fromkeys(names))


def _reject_duplicate_header_reference(
    plan: TableQueryPlan, columns: tuple[ColumnManifest, ...]
) -> None:
    """Refuse when a requested id is an ambiguous original header.

    Args:
        plan: Validated plan.
        columns: Manifest columns.

    Raises:
        TableQueryRefusal: Duplicate original header used as a column id.
    """

    header_counts = Counter(column.original_header for column in columns)
    duplicated = {header for header, count in header_counts.items() if count > 1}
    if not duplicated:
        return
    requested = set(_requested_columns(plan))
    internal = {column.column_name for column in columns}
    for name in requested:
        if name in duplicated and name not in internal:
            raise TableQueryRefusal("duplicate_header_reference")
        matching = [column for column in columns if column.original_header == name]
        if len(matching) > 1:
            raise TableQueryRefusal("duplicate_header_reference")


def _reject_formula_aggregation(
    plan: TableQueryPlan,
    table: AuthorizedTable,
    by_id: dict[str, ColumnManifest],
) -> None:
    """Refuse numeric aggregation over formula or non-numeric columns.

    Args:
        plan: Validated plan.
        table: Authorized artifact.
        by_id: Columns by internal id.

    Raises:
        TableQueryRefusal: Missing/stale formula cache or unsupported type.
    """

    numeric_ops = {
        TableAggregationOp.SUM,
        TableAggregationOp.AVERAGE,
        TableAggregationOp.MIN,
        TableAggregationOp.MAX,
    }
    targets: list[tuple[TableAggregationOp, str]] = [
        (item.op, item.column) for item in plan.aggregations if item.column is not None
    ]
    if plan.comparison is not None:
        targets.append((plan.comparison.aggregation, plan.comparison.column))
    for op, column_id in targets:
        if op not in numeric_ops:
            continue
        column = by_id[column_id]
        if column_id in table.formula_columns:
            raise TableQueryRefusal("missing_formula_cache")
        if column.column_type not in {"integer", "float", "decimal"}:
            raise TableQueryRefusal("unsupported_formula_or_type")


def _reject_mixed_units(plan: TableQueryPlan, by_id: dict[str, ColumnManifest]) -> None:
    """Refuse aggregations that mix units or currencies.

    Args:
        plan: Validated plan.
        by_id: Columns by internal id.

    Raises:
        TableQueryRefusal: Mixed units/currencies without conversion.
    """

    unit_columns = [
        by_id[item.column]
        for item in plan.aggregations
        if item.column is not None and item.column in by_id
    ]
    if plan.comparison is not None and plan.comparison.column in by_id:
        unit_columns.append(by_id[plan.comparison.column])
    measures = {
        column.unit or column.currency
        for column in unit_columns
        if column.unit or column.currency
    }
    if len(measures) > 1:
        raise TableQueryRefusal("mixed_units_or_currency")
    expected = next(iter(measures), None)
    if expected and plan.units and plan.units != expected:
        raise TableQueryRefusal("mixed_units_or_currency")
