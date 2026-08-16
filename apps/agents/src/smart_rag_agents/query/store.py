"""Postgres LangGraph store factory. Runtime never calls ``PostgresStore.setup()``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias, cast

from langgraph.store.postgres import PostgresStore
from langgraph.store.postgres.base import MIGRATIONS
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from smart_rag_core.memory.payload import (
    StorePayloadError,
    validate_memory_store_payload,
)

StoreConnection: TypeAlias = Connection[DictRow]
StorePool: TypeAlias = ConnectionPool[StoreConnection]

EXPECTED_STORE_VERSIONS: tuple[int, ...] = tuple(range(len(MIGRATIONS)))
"""Official ``PostgresStore.MIGRATIONS`` indices that must already exist."""


class StoreSchemaError(RuntimeError):
    """Raised when the ``langgraph.store`` schema does not match the pin."""


def _configure_store_connection(connection: StoreConnection) -> None:
    """Bind one pooled connection to the checkpointer role and search path.

    Args:
        connection: Fresh pool connection before first query.

    Side Effects:
        ``SET ROLE app_checkpointer`` and ``SET search_path TO langgraph, pg_catalog``.
    """

    connection.execute("SET ROLE app_checkpointer")
    connection.execute("SET search_path TO langgraph, pg_catalog")


def assert_store_schema_ready(connection: StoreConnection) -> None:
    """Require store migration versions to match the pinned library.

    Args:
        connection: Connection already configured for schema ``langgraph``.

    Raises:
        StoreSchemaError: When versions are missing. Callers must apply
            Supabase migrations rather than ``PostgresStore.setup()``.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT v FROM store_migrations ORDER BY v")
        versions = tuple(int(row["v"]) for row in cursor.fetchall())
    if versions != EXPECTED_STORE_VERSIONS:
        raise StoreSchemaError(
            "langgraph store schema versions "
            f"{list(versions)} do not match pinned PostgresStore migrations "
            f"{list(EXPECTED_STORE_VERSIONS)}; apply Supabase migrations "
            "and do not call PostgresStore.setup() at runtime"
        )


@dataclass(slots=True)
class QueryMemoryStore:
    """Long-lived PostgresStore plus the pool it borrows.

    Attributes:
        pool: Autocommit pool configured as ``app_checkpointer``.
        store: LangGraph store. ``setup()`` is never invoked.
    """

    pool: StorePool
    store: PostgresStore

    def close(self) -> None:
        """Close the underlying connection pool.

        Side Effects:
            Stops accepting new store connections for this process.
        """

        self.pool.close()

    def put_compact(
        self,
        namespace: tuple[str, str, str],
        key: str,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        """Validate then write one compact summary/preferences item.

        Args:
            namespace: Company/user/conversation namespace.
            key: Store key such as ``summary``.
            payload: Candidate mapping.

        Returns:
            The validated payload.

        Raises:
            StorePayloadError: When the payload includes source-document keys.

        Side Effects:
            Writes ``langgraph.store``. Never calls ``setup()``.
        """

        compact = validate_memory_store_payload(payload)
        self.store.put(namespace, key, compact)
        return compact

    def get_compact(
        self,
        namespace: tuple[str, str, str],
        key: str,
    ) -> dict[str, object] | None:
        """Read one store item and reject source-document payloads.

        Args:
            namespace: Company/user/conversation namespace.
            key: Store key.

        Returns:
            Validated mapping, or ``None`` when missing or invalid.
        """

        item = self.store.get(namespace, key)
        if item is None:
            return None
        try:
            return validate_memory_store_payload(cast(Mapping[str, object], item.value))
        except StorePayloadError:
            return None


def open_query_memory_store(dsn: str, *, max_size: int = 4) -> QueryMemoryStore:
    """Open a PostgresStore against the migrated ``langgraph`` schema.

    Args:
        dsn: Session/direct Postgres URL.
        max_size: Pool ceiling.

    Returns:
        Store wrapper. Caller must ``close()`` on shutdown.

    Raises:
        StoreSchemaError: When store migrations 0-3 are not present.

    Side Effects:
        Opens a connection pool. Does not auto-migrate. Does not apply
        ``VECTOR_MIGRATIONS``.
    """

    pool = ConnectionPool[StoreConnection](
        conninfo=dsn,
        min_size=1,
        max_size=max(1, max_size),
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        configure=_configure_store_connection,
        open=True,
    )
    try:
        with pool.connection() as connection:
            assert_store_schema_ready(connection)
    except Exception:
        pool.close()
        raise
    store = PostgresStore(conn=pool)
    return QueryMemoryStore(pool=pool, store=store)
