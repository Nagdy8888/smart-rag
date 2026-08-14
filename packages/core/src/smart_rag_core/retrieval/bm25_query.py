"""Typed ParadeDB BM25 query constructor. Raw ``pdb.parse`` is not exposed."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import sql

from smart_rag_core.retrieval.profiles import (
    BM25_FIELD_PRIORITY,
    BM25_OPERATOR_SQL,
    MAX_NORMALIZED_QUERY_CHARS,
    Bm25Field,
    Bm25Operator,
)
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1


class Bm25QueryError(ValueError):
    """Raised when a BM25 query uses a disallowed field or operator."""


@dataclass(frozen=True, slots=True)
class Bm25StructuredQuery:
    """One parameterized field query.

    Attributes:
        field: Allow-listed indexed column.
        operator: Allow-listed match operator.
        query_normalized: ``arabic_norm_v1`` query text.
    """

    field: Bm25Field
    operator: Bm25Operator
    query_normalized: str


def build_bm25_query(
    *,
    query_text: str,
    operator: Bm25Operator,
    field: Bm25Field,
) -> Bm25StructuredQuery:
    """Build one typed BM25 field query.

    Args:
        query_text: Raw query text. Normalized before the operator is applied.
        operator: Allow-listed ParadeDB operator.
        field: Allow-listed indexed field.

    Returns:
        Frozen structured query.

    Raises:
        Bm25QueryError: If the field/operator is not allow-listed or the
            normalized query is empty.
    """

    if field not in BM25_FIELD_PRIORITY:
        raise Bm25QueryError("unknown_bm25_field")
    if operator not in BM25_OPERATOR_SQL:
        raise Bm25QueryError("unknown_bm25_operator")
    query_normalized = normalize_arabic_v1(query_text)[:MAX_NORMALIZED_QUERY_CHARS]
    if query_normalized == "":
        raise Bm25QueryError("empty_bm25_query")
    return Bm25StructuredQuery(
        field=field,
        operator=operator,
        query_normalized=query_normalized,
    )


def bm25_match_clause(query: Bm25StructuredQuery) -> sql.Composed:
    """Return ``field operator %s`` with allow-listed identifiers only.

    Args:
        query: Typed field query.

    Returns:
        Composed SQL fragment. The query string remains a bound parameter.
    """

    if query.operator is Bm25Operator.MATCH_DISJUNCTION:
        operator_sql = sql.SQL("|||")
    elif query.operator is Bm25Operator.MATCH_CONJUNCTION:
        operator_sql = sql.SQL("&&&")
    elif query.operator is Bm25Operator.PHRASE:
        operator_sql = sql.SQL("###")
    else:
        raise Bm25QueryError("unknown_bm25_operator")
    return sql.SQL("{field} {operator} %s").format(
        field=sql.Identifier(query.field.value),
        operator=operator_sql,
    )
