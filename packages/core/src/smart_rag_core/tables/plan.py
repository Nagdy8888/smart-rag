"""Declarative TableQueryPlan. Extra fields and SQL/paths are forbidden."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smart_rag_core.tables.limits import (
    TABLE_MAX_GROUP_BY,
    TABLE_MAX_OUTPUT_BYTES,
    TABLE_MAX_OUTPUT_ROWS,
    TABLE_MAX_PREDICATES,
)

_COLUMN_RE = r"^[A-Za-z_][A-Za-z0-9_]*$"


class TablePredicateOperator(StrEnum):
    """Allow-listed comparison operators. No SQL fragments."""

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    IN = "in"


class TableAggregationOp(StrEnum):
    """Allow-listed aggregations bound by table intent."""

    SUM = "sum"
    COUNT = "count"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"


class TableSortDirection(StrEnum):
    """Allow-listed sort directions."""

    ASC = "asc"
    DESC = "desc"


class TablePredicate(BaseModel):
    """One typed predicate over an internal column id.

    Attributes:
        column: Stable internal column id, not a header label.
        operator: Allow-listed operator.
        value: Scalar or, for ``in``, a tuple of scalars.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    column: str = Field(pattern=_COLUMN_RE, max_length=64)
    operator: TablePredicateOperator
    value: Any

    @field_validator("value")
    @classmethod
    def _reject_sqlish_value(cls, value: Any) -> Any:
        """Reject path/SQL-shaped values in predicate payloads.

        Args:
            value: Predicate value.

        Returns:
            The value when it is a bounded scalar or scalar tuple.

        Raises:
            ValueError: If the value looks like SQL, a path, or a mapping.
        """

        if isinstance(value, dict):
            raise ValueError("predicate value must be a scalar")
        if isinstance(value, list):
            items: list[object] = list(cast(list[object], value))
        elif isinstance(value, tuple):
            items = list(cast(tuple[object, ...], value))
        else:
            return _reject_scalar(value)
        if len(items) > 32:
            raise ValueError("in-list exceeds 32 values")
        return tuple(_reject_scalar(item) for item in items)


class TableAggregation(BaseModel):
    """One aggregation over an internal column, or COUNT(*).

    Attributes:
        op: Aggregation operator.
        column: Internal column id. Required except for COUNT.
        alias: Result column name.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: TableAggregationOp
    column: str | None = Field(default=None, pattern=_COLUMN_RE, max_length=64)
    alias: str = Field(pattern=_COLUMN_RE, max_length=64)

    @model_validator(mode="after")
    def _count_may_omit_column(self) -> TableAggregation:
        """Require a column except for COUNT.

        Returns:
            This aggregation.

        Raises:
            ValueError: If a non-count aggregation omits a column.
        """

        if self.op is not TableAggregationOp.COUNT and self.column is None:
            raise ValueError("aggregation requires a column")
        return self


class TableOrder(BaseModel):
    """One order-by clause over an internal column or aggregation alias."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    column: str = Field(pattern=_COLUMN_RE, max_length=64)
    direction: TableSortDirection = TableSortDirection.ASC


class TableComparison(BaseModel):
    """Compare one aggregation under two predicate sets.

    Attributes:
        aggregation: Aggregation applied to both sides.
        column: Internal column id.
        left: Left-hand predicates.
        right: Right-hand predicates.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    aggregation: TableAggregationOp
    column: str = Field(pattern=_COLUMN_RE, max_length=64)
    left: tuple[TablePredicate, ...] = Field(
        default_factory=tuple, max_length=TABLE_MAX_PREDICATES
    )
    right: tuple[TablePredicate, ...] = Field(
        default_factory=tuple, max_length=TABLE_MAX_PREDICATES
    )


class TableQueryPlan(BaseModel):
    """Validated declarative table plan. No SQL, paths, or functions.

    Attributes:
        table_id: Authorized table UUID.
        version_id: Current document version UUID.
        columns: Projected internal column ids when not aggregating.
        predicates: Typed filters.
        aggregations: Allow-listed aggregations.
        group_by: Grouping column ids.
        order_by: Ordering clauses.
        comparison: Optional two-sided aggregation comparison.
        units: Required result unit when mixed-unit columns exist.
        row_limit: Output row cap.
        output_byte_limit: Serialized output cap.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    table_id: UUID
    version_id: UUID
    columns: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    predicates: tuple[TablePredicate, ...] = Field(
        default_factory=tuple, max_length=TABLE_MAX_PREDICATES
    )
    aggregations: tuple[TableAggregation, ...] = Field(
        default_factory=tuple, max_length=8
    )
    group_by: tuple[str, ...] = Field(
        default_factory=tuple, max_length=TABLE_MAX_GROUP_BY
    )
    order_by: tuple[TableOrder, ...] = Field(default_factory=tuple, max_length=8)
    comparison: TableComparison | None = None
    units: str | None = Field(default=None, max_length=32)
    row_limit: int = Field(default=100, ge=1, le=TABLE_MAX_OUTPUT_ROWS)
    output_byte_limit: int = Field(default=65_536, ge=1, le=TABLE_MAX_OUTPUT_BYTES)

    @field_validator("columns", "group_by")
    @classmethod
    def _column_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject non-identifier column ids.

        Args:
            value: Column id tuple.

        Returns:
            The tuple when every id matches the identifier pattern.

        Raises:
            ValueError: If an id is not a safe identifier.
        """

        pattern = re.compile(_COLUMN_RE)
        for item in value:
            if not pattern.fullmatch(item):
                raise ValueError("column id is not an internal identifier")
        return value

    @model_validator(mode="after")
    def _require_operation(self) -> TableQueryPlan:
        """Require a calculation operation; ordinary lookup stays Hybrid.

        Returns:
            This plan.

        Raises:
            ValueError: If the plan has no filter, sort, group, aggregation,
                or comparison.
        """

        if not (
            self.predicates
            or self.aggregations
            or self.group_by
            or self.order_by
            or self.comparison is not None
        ):
            raise ValueError("ordinary lookup stays Hybrid")
        return self


def _reject_scalar(value: Any) -> Any:
    """Reject SQL/path-shaped scalars.

    Args:
        value: Candidate scalar.

    Returns:
        The scalar.

    Raises:
        ValueError: If the value is not a bounded JSON scalar.
    """

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        lowered = value.casefold()
        if any(
            token in lowered
            for token in ("select ", " attach", "../", "://", "pragma", "copy ", ";")
        ):
            raise ValueError("predicate value looks like SQL or a path")
        if len(value) > 256:
            raise ValueError("predicate value exceeds 256 characters")
        return value
    raise ValueError("unsupported predicate value type")
