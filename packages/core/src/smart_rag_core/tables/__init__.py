"""Structured-table query plan, sandbox, and provenance."""

from smart_rag_core.tables.builder import TableQueryCompileError, compile_table_query
from smart_rag_core.tables.plan import (
    TableAggregation,
    TableAggregationOp,
    TableComparison,
    TableOrder,
    TablePredicate,
    TablePredicateOperator,
    TableQueryPlan,
    TableSortDirection,
)
from smart_rag_core.tables.refusals import TableQueryRefusal
from smart_rag_core.tables.resolver import (
    MemoryTableResolver,
    PostgresTableResolver,
    TableResolveError,
)
from smart_rag_core.tables.service import (
    StructuredTableError,
    should_bind_structured_table,
    structured_table_query,
)
from smart_rag_core.tables.types import AuthorizedTable, TableQueryResult

__all__ = [
    "AuthorizedTable",
    "MemoryTableResolver",
    "PostgresTableResolver",
    "StructuredTableError",
    "TableAggregation",
    "TableAggregationOp",
    "TableComparison",
    "TableOrder",
    "TablePredicate",
    "TablePredicateOperator",
    "TableQueryCompileError",
    "TableQueryPlan",
    "TableQueryRefusal",
    "TableQueryResult",
    "TableResolveError",
    "TableSortDirection",
    "compile_table_query",
    "should_bind_structured_table",
    "structured_table_query",
]
