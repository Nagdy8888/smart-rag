"""Typed ParadeDB BM25 query constructor. Raw ``pdb.parse`` is not exposed."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

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


def bm25_key_scope_sql(
    chunk_ids: tuple[UUID, ...] | None,
) -> tuple[sql.Composed, tuple[object, ...]]:
    """Return a key-field scope fragment for one BM25 scored statement.

    ``pg_search`` 0.25.2 raises ``XX000`` (unsupported query shape) when
    ``version_id`` appears in the same ``WHERE`` as ``pdb.score``. The BM25
    index key is ``chunk_id``, so version scope is applied as
    ``chunk_id = ANY(%s::uuid[])`` after a btree lookup of current-version ids.

    Args:
        chunk_ids: Current-version chunk ids, or ``None`` to leave the
            scan unscoped.

    Returns:
        Composed SQL (possibly empty) and bound parameters.

    Raises:
        Bm25QueryError: Empty tuple would match nothing. Callers must
            return an empty ``Bm25RetrievalResult`` instead of querying.
    """

    if chunk_ids is None:
        return sql.SQL(""), ()
    if not chunk_ids:
        raise Bm25QueryError("empty_bm25_key_scope")
    return sql.SQL("AND chunk_id = ANY(%s::uuid[])"), (list(chunk_ids),)
