"""Contract tests for structured-table resolver grants and fail-closed RPC."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pyarrow as pa
import pytest
from smart_rag_core.ingestion.tables import parquet_io
from smart_rag_core.ingestion.tables.schema import PROVENANCE_COLUMN, ROW_INDEX_COLUMN
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tables.plan import (
    TableAggregation,
    TableAggregationOp,
    TableQueryPlan,
)
from smart_rag_core.tables.resolver import PostgresTableResolver, TableResolveError
from smart_rag_core.tables.service import structured_table_query

from tests.contract.hybrid_retrieval_seed import seed_hybrid_retrieval_fixture
from tests.contract.integration_support import resolve_supabase_db_url, try_connect


def _arrow_type(name: str) -> object:
    """Return one pyarrow dtype by name without relying on untyped stubs.

    Args:
        name: ``pyarrow`` factory attribute such as ``string`` or ``int64``.

    Returns:
        The constructed dtype object.
    """

    factory: Callable[[], object] = getattr(pa, name)
    return factory()


def _write_parquet(
    *,
    columns: list[tuple[str, object]],
    rows: list[dict[str, object]],
) -> bytes:
    """Write Parquet bytes through the production helper with explicit types.

    Args:
        columns: Logical column name and dtype pairs.
        rows: Row dictionaries including provenance fields.

    Returns:
        In-memory Parquet payload.
    """

    writer: Callable[..., tuple[object, object]] = parquet_io.write_parquet_artifact
    payload, _schema = writer(columns=columns, rows=rows)
    return bytes(payload)


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield Postgres or skip when local Supabase is unreachable.

    Yields:
        Superuser connection.
    """

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def _write_sales(path: Path) -> str:
    """Write the shared three-row sales Parquet used by Packet 7 contracts.

    Args:
        path: Destination file.

    Returns:
        SHA-256 of the bytes.
    """

    payload = _write_parquet(
        columns=[("dept", _arrow_type("string")), ("amount", _arrow_type("int64"))],
        rows=[
            {
                "dept": "ops",
                "amount": 10,
                ROW_INDEX_COLUMN: 0,
                PROVENANCE_COLUMN: '{"sheet":"Summary","range":"B2"}',
                "__schema_version": "table_parquet_v1",
            },
            {
                "dept": "ops",
                "amount": 15,
                ROW_INDEX_COLUMN: 1,
                PROVENANCE_COLUMN: '{"sheet":"Summary","range":"B3"}',
                "__schema_version": "table_parquet_v1",
            },
            {
                "dept": "hr",
                "amount": 7,
                ROW_INDEX_COLUMN: 2,
                PROVENANCE_COLUMN: '{"sheet":"Summary","range":"B4"}',
                "__schema_version": "table_parquet_v1",
            },
        ],
    )
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_resolve_structured_table_is_app_api_only(
    db_connection: psycopg.Connection,
) -> None:
    """Anon cannot execute the resolver; app_api gets zero rows for unknown ids."""

    table_id = uuid4()
    version_id = uuid4()
    user_id = uuid4()
    with db_connection.cursor() as cursor:
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT count(*) FROM app.resolve_structured_table(
              %s::uuid, 'member'::text, 1::bigint, %s::uuid, %s::uuid
            )
            """,
            (user_id, table_id, version_id),
        )
        row = cursor.fetchone()
        assert row is not None
        assert int(row[0]) == 0
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                """
                SELECT * FROM app.resolve_structured_table(
                  %s::uuid, 'member'::text, 1::bigint, %s::uuid, %s::uuid
                )
                """,
                (user_id, table_id, version_id),
            )
    db_connection.rollback()
    with db_connection.cursor() as cursor:
        cursor.execute("RESET ROLE")


def test_resolve_structured_table_idor_and_stale_version(
    db_connection: psycopg.Connection, tmp_path: Path
) -> None:
    """Member cannot read restricted/stale/deleted tables; owner can read ACL."""

    parquet = tmp_path / "sales.parquet"
    digest = _write_sales(parquet)
    local_root = tmp_path / "artifacts"
    local_root.mkdir()
    (local_root / f"{digest}.parquet").write_bytes(parquet.read_bytes())
    seed = seed_hybrid_retrieval_fixture(db_connection)
    visible_table_id = uuid4()
    restricted_table_id = uuid4()
    stale_table_id = uuid4()
    columns = [
        {
            "column_name": "dept",
            "original_header": "dept",
            "header_ordinal": 0,
            "column_type": "string",
        },
        {
            "column_name": "amount",
            "original_header": "amount",
            "header_ordinal": 1,
            "column_type": "integer",
        },
    ]
    provenance = json.dumps(
        {
            "columns": columns,
            "content_hash_sha256": digest,
            "source_format": "xlsx",
            "workbook_name": "budget.xlsx",
        }
    )
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.document_tables (
              id, document_id, version_id, table_name, sheet_name,
              parquet_bucket, parquet_path, row_count, column_count,
              provenance
            )
            VALUES
              (%s, %s, %s, 'sales', 'Summary', 'table-artifacts', 'p', 3, 2, %s::jsonb),
              (%s, %s, %s, 'restricted', 'Pay', 'table-artifacts', 'p', 3, 2, %s::jsonb),
              (%s, %s, %s, 'stale', 'Old', 'table-artifacts', 'p', 3, 2, %s::jsonb)
            """,
            (
                visible_table_id,
                seed.visible_document_id,
                seed.visible_version_id,
                provenance,
                restricted_table_id,
                seed.restricted_document_id,
                seed.restricted_version_id,
                provenance,
                stale_table_id,
                seed.visible_document_id,
                seed.stale_version_id,
                provenance,
            ),
        )
    db_connection.commit()
    member = CallerContext(
        user_id=str(seed.member_id),
        role=UserRole.MEMBER,
        authorization_version=seed.auth_version,
    )
    owner = CallerContext(
        user_id=str(seed.owner_id),
        role=UserRole.OWNER,
        authorization_version=seed.auth_version,
    )
    resolver = PostgresTableResolver(db_connection, local_root=local_root)
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SET ROLE app_api")
        visible = structured_table_query(
            TableQueryPlan(
                table_id=visible_table_id,
                version_id=seed.visible_version_id,
                aggregations=(
                    TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                ),
            ),
            caller=member,
            resolver=resolver,
        )
        assert int(visible.rows[0]["n"]) == 3
        with pytest.raises(TableResolveError):
            structured_table_query(
                TableQueryPlan(
                    table_id=restricted_table_id,
                    version_id=seed.restricted_version_id,
                    aggregations=(
                        TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                    ),
                ),
                caller=member,
                resolver=resolver,
            )
        owner_restricted = structured_table_query(
            TableQueryPlan(
                table_id=restricted_table_id,
                version_id=seed.restricted_version_id,
                aggregations=(
                    TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                ),
            ),
            caller=owner,
            resolver=resolver,
        )
        assert int(owner_restricted.rows[0]["n"]) == 3
        with pytest.raises(TableResolveError):
            structured_table_query(
                TableQueryPlan(
                    table_id=stale_table_id,
                    version_id=seed.stale_version_id,
                    aggregations=(
                        TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                    ),
                ),
                caller=member,
                resolver=resolver,
            )
        with db_connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(
                """
                UPDATE app.documents
                SET deleted_at = timezone('utc', now())
                WHERE id = %s
                """,
                (seed.visible_document_id,),
            )
            cursor.execute("SET ROLE app_api")
        with pytest.raises(TableResolveError):
            structured_table_query(
                TableQueryPlan(
                    table_id=visible_table_id,
                    version_id=seed.visible_version_id,
                    aggregations=(
                        TableAggregation(op=TableAggregationOp.COUNT, alias="n"),
                    ),
                ),
                caller=member,
                resolver=resolver,
            )
    finally:
        db_connection.rollback()
        with db_connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
