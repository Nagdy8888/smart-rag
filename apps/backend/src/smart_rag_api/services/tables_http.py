"""Authorized table manifest listing and bounded analysis."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.tables.plan import TableQueryPlan
from smart_rag_core.tables.refusals import TableQueryRefusal
from smart_rag_core.tables.resolver import PostgresTableResolver, TableResolveError
from smart_rag_core.tables.service import StructuredTableError, structured_table_query
from smart_rag_core.tables.types import TableQueryResult

from smart_rag_api.storage_admin.objects import StorageAdminError, download_object
from smart_rag_api.storage_admin.settings import load_privileged_storage_settings


@dataclass(frozen=True, slots=True)
class TableManifestRecord:
    """ACL-visible current-version table manifest. No storage paths."""

    table_id: UUID
    document_id: UUID
    version_id: UUID
    table_name: str
    sheet_name: str | None
    row_count: int | None
    column_count: int | None


class TableHttpService:
    """Factory-injected table operations."""

    def __init__(self, postgres_url: str, *, artifact_root: Path | None = None) -> None:
        """Store DSN and optional local Parquet root.

        Args:
            postgres_url: app_api URL.
            artifact_root: Directory of fetched Parquet files named by hash.
        """

        self._postgres_url = postgres_url
        self._artifact_root = artifact_root

    def list_manifests(
        self,
        caller: CallerContext,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[TableManifestRecord, ...]:
        """List authorized current-version table manifests.

        Args:
            caller: Authenticated caller.
            limit: Page size, max 50.
            offset: Page offset.

        Returns:
            Manifest records without Parquet paths.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT table_id, document_id, version_id, table_name, sheet_name,
                           row_count, column_count
                    FROM app.list_authorized_table_manifests(%s, %s, %s, %s, %s)
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        limit,
                        offset,
                    ),
                )
                rows = cursor.fetchall()
        records: list[TableManifestRecord] = []
        for row in rows:
            records.append(
                TableManifestRecord(
                    table_id=row["table_id"],
                    document_id=row["document_id"],
                    version_id=row["version_id"],
                    table_name=str(row["table_name"]),
                    sheet_name=row.get("sheet_name"),
                    row_count=row.get("row_count"),
                    column_count=row.get("column_count"),
                )
            )
        return tuple(records)

    def analyze(
        self, caller: CallerContext, *, plan: TableQueryPlan
    ) -> TableQueryResult:
        """Execute one authorized TableQueryPlan.

        Args:
            caller: Authenticated caller.
            plan: Validated extra-forbid plan.

        Returns:
            Deterministic values plus provenance.

        Raises:
            QueryAdmissionError: Unauthorized or missing artifact.
            StructuredTableError: Sandbox/recheck failure.
        """

        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                if self._artifact_root is not None:
                    resolver = PostgresTableResolver(
                        connection, local_root=self._artifact_root
                    )
                    return structured_table_query(
                        plan, caller=caller, resolver=resolver
                    )
                with TemporaryDirectory(prefix="smart-rag-table-") as directory:
                    root = Path(directory)
                    materialize_table_artifact(
                        connection, caller=caller, plan=plan, root=root
                    )
                    resolver = PostgresTableResolver(connection, local_root=root)
                    return structured_table_query(
                        plan, caller=caller, resolver=resolver
                    )
        except TableResolveError as exc:
            raise QueryAdmissionError("not_found") from exc
        except TableQueryRefusal as exc:
            raise StructuredTableError("table_plan_rejected") from exc
        except StructuredTableError:
            raise


def materialize_table_artifact(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    plan: TableQueryPlan,
    root: Path,
) -> None:
    """Fetch one RPC-authorized, hash-verified artifact into a private temp root.

    Storage coordinates are server-derived. The resolver and executor repeat
    authorization checks before and after execution. Downloads stop at 32 MiB.
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "SELECT parquet_bucket, parquet_path, provenance FROM "
            "app.resolve_structured_table(%s::uuid, %s::text, %s::bigint, %s::uuid, %s::uuid)",
            (
                caller.rpc_user_id(),
                caller.role.value,
                caller.authorization_version,
                plan.table_id,
                plan.version_id,
            ),
        )
        row = cursor.fetchone()
    if row is None:
        raise TableResolveError("table_not_authorized")
    provenance = row.get("provenance")
    digest = (
        cast(dict[str, object], provenance).get("content_hash_sha256")
        if isinstance(provenance, dict)
        else None
    )
    bucket, path = row.get("parquet_bucket"), row.get("parquet_path")
    if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise StructuredTableError("table_artifact_unavailable")
    if not isinstance(bucket, str) or not isinstance(path, str):
        raise StructuredTableError("table_artifact_unavailable")
    try:
        payload = download_object(
            load_privileged_storage_settings(),
            bucket=bucket,
            object_path=path,
            timeout_seconds=20,
            max_bytes=32 * 1024 * 1024,
        )
        if hashlib.sha256(payload).hexdigest() != digest:
            raise StructuredTableError("table_artifact_unavailable")
        (root / f"{digest}.parquet").write_bytes(payload)
    except (StorageAdminError, ValueError, OSError) as exc:
        raise StructuredTableError("table_artifact_unavailable") from exc
