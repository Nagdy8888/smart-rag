"""Compile a TableQueryPlan into parameterized DuckDB SQL.

Identifiers come only from the allow-listed internal column set. Values are
positional parameters. The plan never supplies SQL.
"""

# ruff: noqa: S608

from __future__ import annotations

import re
from typing import cast

from smart_rag_core.ingestion.tables.schema import PROVENANCE_COLUMN
from smart_rag_core.tables.limits import ALLOWED_TABLE, TABLE_MAX_SCANNED_ROWS
from smart_rag_core.tables.plan import (
    TableAggregation,
    TableAggregationOp,
    TablePredicate,
    TablePredicateOperator,
    TableQueryPlan,
)
from smart_rag_core.tables.types import CompiledTableQuery

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BLOCKED_SQL = re.compile(
    r"\b(?:attach|copy|install|load|pragma|create|drop|insert|update|"
    r"delete|alter)\b|://|\.\./",
    re.IGNORECASE,
)
_OPERATOR_SQL = {
    TablePredicateOperator.EQ: "=",
    TablePredicateOperator.NE: "<>",
    TablePredicateOperator.LT: "<",
    TablePredicateOperator.LE: "<=",
    TablePredicateOperator.GT: ">",
    TablePredicateOperator.GE: ">=",
}
_AGG_SQL = {
    TableAggregationOp.SUM: "SUM",
    TableAggregationOp.COUNT: "COUNT",
    TableAggregationOp.AVERAGE: "AVG",
    TableAggregationOp.MIN: "MIN",
    TableAggregationOp.MAX: "MAX",
}


class TableQueryCompileError(ValueError):
    """The plan cannot be compiled against the authorized schema."""


def quote_ident(name: str, *, allowed: frozenset[str]) -> str:
    """Quote one allow-listed identifier.

    Args:
        name: Internal column or alias.
        allowed: Allow-listed names.

    Returns:
        Double-quoted identifier.

    Raises:
        TableQueryCompileError: If the name is not allow-listed.
    """

    if name not in allowed or not _IDENT.fullmatch(name):
        raise TableQueryCompileError(f"column_not_allowlisted:{name}")
    return f'"{name}"'


def compile_table_query(
    plan: TableQueryPlan, *, allowed_columns: frozenset[str]
) -> CompiledTableQuery:
    """Compile one plan into SELECT SQL with bound parameters.

    Args:
        plan: Validated declarative plan.
        allowed_columns: Internal ids from the authorized manifest.

    Returns:
        Compiled SQL and parameter tuples.

    Raises:
        TableQueryCompileError: If a column is unknown or the plan is empty.
    """

    aliases = {item.alias for item in plan.aggregations}
    ident_allowed = allowed_columns | aliases | {"allowed_table"}
    if plan.comparison is not None:
        return _compile_comparison(plan, allowed_columns=allowed_columns)
    select_sql, params = _select_clause(plan, allowed_columns=allowed_columns)
    where_sql, where_params = _where_clause(
        plan.predicates, allowed_columns=allowed_columns
    )
    params = (*params, *where_params)
    group_sql = ""
    if plan.group_by:
        group_sql = " GROUP BY " + ", ".join(
            quote_ident(name, allowed=allowed_columns) for name in plan.group_by
        )
    order_sql = _order_clause(plan, ident_allowed=ident_allowed)
    limit = min(plan.row_limit, TABLE_MAX_SCANNED_ROWS)
    sql = (
        f"SELECT {select_sql} FROM {ALLOWED_TABLE}{where_sql}{group_sql}"
        f"{order_sql} LIMIT {limit}"
    )
    count_sql = f"SELECT COUNT(*) FROM {ALLOWED_TABLE}{where_sql}"
    provenance_sql = (
        f"SELECT DISTINCT {_provenance_ident()} FROM {ALLOWED_TABLE}{where_sql}"
    )
    _assert_safe_sql(sql)
    _assert_safe_sql(count_sql)
    _assert_safe_sql(provenance_sql)
    return CompiledTableQuery(
        sql=sql,
        params=params,
        count_sql=count_sql,
        count_params=where_params,
        provenance_sql=provenance_sql,
        provenance_params=where_params,
    )


def _select_clause(
    plan: TableQueryPlan, *, allowed_columns: frozenset[str]
) -> tuple[str, tuple[object, ...]]:
    """Build the SELECT list.

    Args:
        plan: Validated plan.
        allowed_columns: Manifest column ids.

    Returns:
        SELECT fragment and extra parameters (always empty).
    """

    parts: list[str] = []
    if plan.aggregations:
        parts.extend(
            quote_ident(name, allowed=allowed_columns) for name in plan.group_by
        )
        for item in plan.aggregations:
            parts.append(_agg_expr(item, allowed_columns=allowed_columns))
        if plan.columns:
            extra = [name for name in plan.columns if name not in plan.group_by]
            if extra:
                raise TableQueryCompileError("projected_column_not_grouped")
    else:
        targets = plan.columns or tuple(sorted(allowed_columns))
        parts.extend(quote_ident(name, allowed=allowed_columns) for name in targets)
    if not parts:
        raise TableQueryCompileError("empty_select")
    return ", ".join(parts), ()


def _agg_expr(item: TableAggregation, *, allowed_columns: frozenset[str]) -> str:
    """Return one aggregation expression.

    Args:
        item: Aggregation spec.
        allowed_columns: Manifest column ids.

    Returns:
        SQL aggregation with alias.
    """

    fn = _AGG_SQL[item.op]
    alias = quote_ident(item.alias, allowed=frozenset({item.alias}))
    if item.op is TableAggregationOp.COUNT and item.column is None:
        return f"{fn}(*) AS {alias}"
    column = quote_ident(item.column or "", allowed=allowed_columns)
    return f"{fn}({column}) AS {alias}"


def _where_clause(
    predicates: tuple[TablePredicate, ...], *, allowed_columns: frozenset[str]
) -> tuple[str, tuple[object, ...]]:
    """Compile AND-ed predicates.

    Args:
        predicates: Typed predicates.
        allowed_columns: Manifest column ids.

    Returns:
        WHERE fragment (possibly empty) and bound parameters.
    """

    if not predicates:
        return "", ()
    parts: list[str] = []
    params: list[object] = []
    for predicate in predicates:
        column = quote_ident(predicate.column, allowed=allowed_columns)
        if predicate.operator is TablePredicateOperator.IN:
            raw_in: object = predicate.value
            if isinstance(raw_in, tuple):
                values = cast(tuple[object, ...], raw_in)
            else:
                values = (raw_in,)
            if not values:
                raise TableQueryCompileError("empty_in_list")
            placeholders = ", ".join("?" for _ in values)
            parts.append(f"{column} IN ({placeholders})")
            params.extend(values)
            continue
        sql_op = _OPERATOR_SQL[predicate.operator]
        parts.append(f"{column} {sql_op} ?")
        params.append(predicate.value)
    return " WHERE " + " AND ".join(parts), tuple(params)


def _order_clause(plan: TableQueryPlan, *, ident_allowed: frozenset[str]) -> str:
    """Compile ORDER BY.

    Args:
        plan: Validated plan.
        ident_allowed: Columns plus aggregation aliases.

    Returns:
        ORDER BY fragment or empty string.
    """

    if not plan.order_by:
        return ""
    parts: list[str] = []
    for item in plan.order_by:
        ident = quote_ident(item.column, allowed=ident_allowed)
        direction = "ASC" if item.direction.value == "asc" else "DESC"
        parts.append(f"{ident} {direction}")
    return " ORDER BY " + ", ".join(parts)


def _compile_comparison(
    plan: TableQueryPlan, *, allowed_columns: frozenset[str]
) -> CompiledTableQuery:
    """Compile a two-sided aggregation comparison.

    Args:
        plan: Plan with ``comparison`` set.
        allowed_columns: Manifest column ids.

    Returns:
        Compiled comparison query.
    """

    comparison = plan.comparison
    if comparison is None:
        raise TableQueryCompileError("missing_comparison")
    fake = TableAggregation(
        op=comparison.aggregation,
        column=comparison.column,
        alias="cmp_value",
    )
    expr = _agg_expr(fake, allowed_columns=allowed_columns).rsplit(" AS ", 1)[0]
    left_where, left_params = _where_clause(
        comparison.left, allowed_columns=allowed_columns
    )
    right_where, right_params = _where_clause(
        comparison.right, allowed_columns=allowed_columns
    )
    sql = (
        f"SELECT (SELECT {expr} FROM {ALLOWED_TABLE}{left_where}) AS left_value, "
        f"(SELECT {expr} FROM {ALLOWED_TABLE}{right_where}) AS right_value"
    )
    prov = _provenance_ident()
    provenance_sql = (
        f"SELECT DISTINCT {prov} FROM {ALLOWED_TABLE}{left_where} "
        f"UNION SELECT DISTINCT {prov} FROM {ALLOWED_TABLE}{right_where}"
    )
    _assert_safe_sql(sql)
    _assert_safe_sql(provenance_sql)
    return CompiledTableQuery(
        sql=sql,
        params=(*left_params, *right_params),
        count_sql=f"SELECT COUNT(*) FROM {ALLOWED_TABLE}",
        count_params=(),
        provenance_sql=provenance_sql,
        provenance_params=(*left_params, *right_params),
    )


def _provenance_ident() -> str:
    """Return the quoted Parquet provenance column identifier.

    Returns:
        Double-quoted ``__provenance_json`` identifier.

    Raises:
        TableQueryCompileError: If the schema constant is not an identifier.
    """

    if not _IDENT.fullmatch(PROVENANCE_COLUMN):
        raise TableQueryCompileError("provenance_column_invalid")
    return f'"{PROVENANCE_COLUMN}"'


def _assert_safe_sql(sql: str) -> None:
    """Fail closed if compiled SQL contains blocked tokens.

    Args:
        sql: Compiler output.

    Raises:
        TableQueryCompileError: If a blocked construct appears.
    """

    lowered = sql.casefold()
    if ";" in lowered:
        raise TableQueryCompileError("blocked_sql:semicolon")
    if _BLOCKED_SQL.search(sql):
        raise TableQueryCompileError("blocked_sql")
    if not lowered.startswith("select "):
        raise TableQueryCompileError("only_select_permitted")
