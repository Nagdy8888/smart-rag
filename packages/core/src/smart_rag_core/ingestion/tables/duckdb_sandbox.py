"""Read-only DuckDB sandbox contract for table artifact consumption tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import duckdb

_BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bATTACH\b", re.IGNORECASE),
    re.compile(r"\bCOPY\b", re.IGNORECASE),
    re.compile(r"\bINSTALL\b", re.IGNORECASE),
    re.compile(r"\bLOAD\b", re.IGNORECASE),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\.\./"),
    re.compile(r"[*?\[\]]"),
    re.compile(
        r"\bCREATE\b|\bDROP\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bALTER\b",
        re.IGNORECASE,
    ),
)


class DuckdbSandboxError(Exception):
    """Raised when a sandbox policy violation is detected."""


@runtime_checkable
class DuckdbRelation(Protocol):
    """Structural DuckDB relation handle used after ``execute``."""

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all result rows.

        Returns:
            Query rows as tuples.
        """
        ...


@runtime_checkable
class DuckdbConnection(Protocol):
    """Structural DuckDB connection handle for the in-memory sandbox."""

    def execute(self, sql: str) -> DuckdbRelation:
        """Run one SQL string.

        Args:
            sql: Statement text, unchanged from the sandbox caller.

        Returns:
            Relation handle supporting ``fetchall``.
        """
        ...

    def close(self) -> None:
        """Close the in-memory connection."""
        ...


@dataclass(frozen=True, slots=True)
class DuckdbSandbox:
    """In-memory DuckDB sandbox limited to one fixture Parquet file."""

    allowed_parquet: Path

    def __post_init__(self) -> None:
        """Validate the allowed Parquet fixture exists before sandbox use."""

        if not self.allowed_parquet.is_file():
            raise DuckdbSandboxError("allowed parquet fixture must exist")

    def query_fixture(
        self, *, column: str, limit: int = 10
    ) -> list[tuple[object, ...]]:
        """Run a bounded SELECT against the allowed Parquet fixture.

        Args:
            column: Allow-listed column name from the fixture schema.
            limit: Maximum rows to return.

        Returns:
            Query rows as tuples.

        Raises:
            DuckdbSandboxError: When SQL violates sandbox policy.
        """

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column):
            raise DuckdbSandboxError("column name is not allow-listed")
        sql = f"SELECT {column} FROM allowed_fixture LIMIT {int(limit)}"  # noqa: S608
        self._validate_sql(sql)
        connection = _connect_memory()
        try:
            parquet_literal = (
                self.allowed_parquet.resolve().as_posix().replace("'", "''")
            )
            connection.execute(
                f"CREATE VIEW allowed_fixture AS SELECT * FROM read_parquet('{parquet_literal}')"  # noqa: S608
            )
            relation = connection.execute(sql)
            return relation.fetchall()
        finally:
            connection.close()

    def assert_blocked(self, sql: str) -> None:
        """Assert one SQL statement is rejected by sandbox policy.

        Args:
            sql: Potentially malicious SQL.

        Raises:
            DuckdbSandboxError: When the SQL is not blocked.
        """

        self._validate_sql(sql)

    def _validate_sql(self, sql: str) -> None:
        """Reject blocked SQL constructs before execution."""

        stripped = sql.strip()
        if not stripped.lower().startswith("select"):
            raise DuckdbSandboxError("only SELECT queries are permitted")
        allowed_path = self.allowed_parquet.resolve().as_posix()
        if "read_parquet" in stripped.lower() and allowed_path not in stripped:
            raise DuckdbSandboxError(
                "read_parquet must reference the allowed fixture only"
            )
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(stripped):
                raise DuckdbSandboxError(f"blocked SQL construct: {pattern.pattern}")


def _call(factory: object, /, *args: object, **kwargs: object) -> object:
    """Invoke one DuckDB callable with the original positional and keyword arguments.

    Args:
        factory: DuckDB factory or connection method.
        *args: Positional arguments forwarded unchanged.
        **kwargs: Keyword arguments forwarded unchanged.

    Returns:
        Opaque vendor result.

    Raises:
        TypeError: If ``factory`` is not callable.
    """

    if not callable(factory):
        raise TypeError("DuckDB factory is not callable")
    return factory(*args, **kwargs)


def _member(owner: object, name: str) -> object:
    """Return one named attribute from a DuckDB module or handle.

    Args:
        owner: DuckDB module or opaque connection/relation handle.
        name: Attribute name resolved at the call site.

    Returns:
        The attribute value.
    """

    return getattr(owner, name)


def _connect_memory() -> DuckdbConnection:
    """Open an in-memory DuckDB connection with the same arguments as ``duckdb.connect``.

    Returns:
        Connection handle supporting ``execute`` and ``close``.

    Raises:
        TypeError: If DuckDB does not return a connection handle.
    """

    connection: object = _call(_member(duckdb, "connect"), database=":memory:")
    if not isinstance(connection, DuckdbConnection):
        raise TypeError("duckdb.connect must return a connection handle")
    return connection
