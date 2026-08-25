"""Structured-table query plan, sandbox, and provenance.

Package exports stay lazy so ``python -m smart_rag_core.tables.sandbox_worker``
does not import Postgres resolvers, DuckDB, or the query service during
process start. The 3-second statement deadline includes worker startup.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

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

_EXPORTS: dict[str, tuple[str, str]] = {
    "AuthorizedTable": ("smart_rag_core.tables.types", "AuthorizedTable"),
    "MemoryTableResolver": ("smart_rag_core.tables.resolver", "MemoryTableResolver"),
    "PostgresTableResolver": (
        "smart_rag_core.tables.resolver",
        "PostgresTableResolver",
    ),
    "StructuredTableError": ("smart_rag_core.tables.service", "StructuredTableError"),
    "TableAggregation": ("smart_rag_core.tables.plan", "TableAggregation"),
    "TableAggregationOp": ("smart_rag_core.tables.plan", "TableAggregationOp"),
    "TableComparison": ("smart_rag_core.tables.plan", "TableComparison"),
    "TableOrder": ("smart_rag_core.tables.plan", "TableOrder"),
    "TablePredicate": ("smart_rag_core.tables.plan", "TablePredicate"),
    "TablePredicateOperator": (
        "smart_rag_core.tables.plan",
        "TablePredicateOperator",
    ),
    "TableQueryCompileError": (
        "smart_rag_core.tables.builder",
        "TableQueryCompileError",
    ),
    "TableQueryPlan": ("smart_rag_core.tables.plan", "TableQueryPlan"),
    "TableQueryRefusal": ("smart_rag_core.tables.refusals", "TableQueryRefusal"),
    "TableQueryResult": ("smart_rag_core.tables.types", "TableQueryResult"),
    "TableResolveError": ("smart_rag_core.tables.resolver", "TableResolveError"),
    "TableSortDirection": ("smart_rag_core.tables.plan", "TableSortDirection"),
    "compile_table_query": ("smart_rag_core.tables.builder", "compile_table_query"),
    "should_bind_structured_table": (
        "smart_rag_core.tables.service",
        "should_bind_structured_table",
    ),
    "structured_table_query": (
        "smart_rag_core.tables.service",
        "structured_table_query",
    ),
}


def __getattr__(name: str) -> Any:
    """Load one public table export on first access.

    Args:
        name: Exported attribute name.

    Returns:
        The named object from its owning submodule.

    Raises:
        AttributeError: If ``name`` is not a public export.
    """

    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return lazy public names for tab-completion.

    Returns:
        Sorted public export names.
    """

    return sorted(__all__)
