"""Resolve table/version IDs to authorized current Parquet artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_core.ingestion.tables.manifest import ColumnManifest
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.tables.types import AuthorizedTable


class TableResolveError(LookupError):
    """Table is missing, unauthorized, stale, or deleted."""


class TableArtifactResolver(Protocol):
    """Server-side table authority. Client paths never participate."""

    def resolve(
        self,
        *,
        table_id: UUID,
        version_id: UUID,
        caller: CallerContext,
    ) -> AuthorizedTable:
        """Return one authorized current artifact.

        Args:
            table_id: Requested table.
            version_id: Requested current version.
            caller: Server-derived caller.

        Returns:
            Authorized table with a local Parquet path.

        Raises:
            TableResolveError: Unauthorized or missing.
        """

        ...

    def recheck(
        self,
        *,
        table_id: UUID,
        version_id: UUID,
        caller: CallerContext,
    ) -> bool:
        """Return whether the table is still authorized after execution.

        Args:
            table_id: Table id.
            version_id: Version id.
            caller: Server-derived caller.

        Returns:
            True when the table remains visible and current.
        """

        ...


@dataclass(frozen=True, slots=True)
class MemoryTableResolver:
    """Test resolver keyed by table and version ids."""

    tables: dict[tuple[UUID, UUID], AuthorizedTable]

    def resolve(
        self,
        *,
        table_id: UUID,
        version_id: UUID,
        caller: CallerContext,
    ) -> AuthorizedTable:
        """Return a preloaded authorized table.

        Args:
            table_id: Requested table.
            version_id: Requested version.
            caller: Ignored except for disabled callers.

        Returns:
            Authorized table.

        Raises:
            TableResolveError: Missing or disabled caller.
        """

        if caller.disabled:
            raise TableResolveError("caller_disabled")
        table = self.tables.get((table_id, version_id))
        if table is None:
            raise TableResolveError("table_not_authorized")
        return table

    def recheck(
        self,
        *,
        table_id: UUID,
        version_id: UUID,
        caller: CallerContext,
    ) -> bool:
        """Return whether the preloaded table is still present.

        Args:
            table_id: Table id.
            version_id: Version id.
            caller: Server-derived caller.

        Returns:
            True when resolve would succeed.
        """

        try:
            self.resolve(table_id=table_id, version_id=version_id, caller=caller)
        except TableResolveError:
            return False
        return True


class PostgresTableResolver:
    """Resolve tables through ``app.resolve_structured_table``.

    The RPC returns storage coordinates. ``local_root`` maps the storage path
    onto a fetched immutable local file for the sandbox. Fetch itself is the
    caller's responsibility before resolve when using this class with a
    pre-materialized file named by content hash.
    """

    def __init__(self, connection: psycopg.Connection, *, local_root: Path) -> None:
        """Store the idle connection and local artifact root.

        Args:
            connection: psycopg connection used inside a retrieval transaction.
            local_root: Directory of fetched Parquet files named by SHA-256.
        """

        self._connection = connection
        self._local_root = local_root

    def resolve(
        self,
        *,
        table_id: UUID,
        version_id: UUID,
        caller: CallerContext,
    ) -> AuthorizedTable:
        """Load one authorized table from the security-invoker RPC.

        Args:
            table_id: Requested table.
            version_id: Requested version.
            caller: Server-derived caller.

        Returns:
            Authorized table whose Parquet exists under ``local_root``.

        Raises:
            TableResolveError: RPC returned no row or the local file is missing.
        """

        row = self._fetch_row(table_id=table_id, version_id=version_id, caller=caller)
        if row is None:
            raise TableResolveError("table_not_authorized")
        provenance = _as_str_map(row.get("provenance"))
        digest = str(
            provenance.get("content_hash_sha256") or row.get("content_hash") or ""
        )
        local = self._local_root / f"{digest}.parquet" if digest else None
        if local is None or not local.is_file():
            raise TableResolveError("local_artifact_missing")
        column_raw = provenance.get("columns")
        if isinstance(column_raw, list):
            column_items = cast(list[object], column_raw)
        else:
            column_items = []
        columns = tuple(ColumnManifest.model_validate(item) for item in column_items)
        nested_map = _as_str_map(provenance.get("provenance"))
        hidden_sheet = bool(provenance.get("hidden_sheet")) or bool(
            nested_map.get("hidden_sheet")
        )
        if any(column.hidden for column in columns):
            hidden_sheet = True
        formula_raw = provenance.get("formula_columns")
        if formula_raw is None:
            formula_raw = nested_map.get("formula_columns")
        if isinstance(formula_raw, list):
            formula_columns = tuple(
                str(item) for item in cast(list[object], formula_raw)
            )
        elif isinstance(formula_raw, tuple):
            formula_columns = tuple(
                str(item) for item in cast(tuple[object, ...], formula_raw)
            )
        else:
            formula_columns = ()
        sheet_raw = row.get("sheet_name")
        return AuthorizedTable(
            table_id=UUID(str(row["table_id"])),
            document_id=UUID(str(row["document_id"])),
            version_id=UUID(str(row["version_id"])),
            table_name=str(row["table_name"]),
            sheet_name=None if sheet_raw is None else str(sheet_raw),
            workbook_name=str(
                provenance.get("workbook_name")
                or nested_map.get("workbook_name")
                or row["table_name"]
            ),
            columns=columns,
            parquet_sha256=digest,
            local_parquet_path=local,
            source_format=str(provenance.get("source_format") or "csv"),
            hidden_sheet=hidden_sheet,
            formula_columns=formula_columns,
        )

    def recheck(
        self,
        *,
        table_id: UUID,
        version_id: UUID,
        caller: CallerContext,
    ) -> bool:
        """Re-run the RPC after execution.

        Args:
            table_id: Table id.
            version_id: Version id.
            caller: Server-derived caller.

        Returns:
            True when the RPC still returns a row.
        """

        return (
            self._fetch_row(table_id=table_id, version_id=version_id, caller=caller)
            is not None
        )

    def _fetch_row(
        self,
        *,
        table_id: UUID,
        version_id: UUID,
        caller: CallerContext,
    ) -> dict[str, object] | None:
        """Execute the resolver RPC.

        Args:
            table_id: Table id.
            version_id: Version id.
            caller: Server-derived caller.

        Returns:
            One row mapping or None.
        """

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                  table_id,
                  document_id,
                  version_id,
                  table_name,
                  sheet_name,
                  parquet_bucket,
                  parquet_path,
                  row_count,
                  column_count,
                  provenance
                FROM app.resolve_structured_table(
                  %s::uuid, %s::text, %s::bigint, %s::uuid, %s::uuid
                )
                """,
                (
                    caller.rpc_user_id(),
                    caller.role.value,
                    caller.authorization_version,
                    table_id,
                    version_id,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        untyped = cast(dict[object, object], dict(row))
        return {str(key): value for key, value in untyped.items()}


def _as_str_map(value: object) -> dict[str, object]:
    """Return a string-keyed mapping from JSON/RPC payloads.

    Args:
        value: Provenance JSON or nested object.

    Returns:
        Empty dict when ``value`` is not a mapping.
    """

    if not isinstance(value, dict):
        return {}
    untyped = cast(dict[object, object], value)
    return {str(key): item for key, item in untyped.items()}
