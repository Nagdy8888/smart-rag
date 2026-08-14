"""Postgres checkpointer factory for ingestion graphs.

Pins runtime wiring to ``langgraph-checkpoint-postgres==3.1.2`` on schema
``langgraph`` as role ``app_checkpointer``. Never calls ``PostgresSaver.setup()``;
Phase 2/3 migrations own DDL.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.base import MIGRATIONS
from langgraph.graph.state import CompiledStateGraph
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

EXPECTED_CHECKPOINT_VERSIONS: tuple[int, ...] = tuple(range(len(MIGRATIONS)))
"""Official ``PostgresSaver.MIGRATIONS`` indices that must already exist."""


class CheckpointerSchemaError(RuntimeError):
    """Raised when the ``langgraph`` schema does not match the pinned library."""


def _configure_checkpointer_connection(connection: Connection) -> None:
    """Bind one pooled connection to the checkpointer role and search path.

    Args:
        connection: Fresh pool connection before first query.

    Side Effects:
        ``SET ROLE app_checkpointer`` and ``SET search_path TO langgraph, pg_catalog``
        so unqualified checkpoint table names hit the Phase 2 schema.
    """

    connection.execute("SET ROLE app_checkpointer")
    connection.execute("SET search_path TO langgraph, pg_catalog")


def assert_checkpointer_schema_ready(connection: Connection) -> None:
    """Require checkpoint migration versions to match the pinned library.

    Args:
        connection: Connection already configured for schema ``langgraph``.

    Raises:
        CheckpointerSchemaError: When versions are missing. Callers must apply
            Supabase migrations rather than ``PostgresSaver.setup()``.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT v FROM checkpoint_migrations ORDER BY v")
        versions = tuple(int(row["v"]) for row in cursor.fetchall())
    if versions != EXPECTED_CHECKPOINT_VERSIONS:
        raise CheckpointerSchemaError(
            "langgraph checkpoint schema versions "
            f"{list(versions)} do not match pinned "
            f"langgraph-checkpoint-postgres migrations "
            f"{list(EXPECTED_CHECKPOINT_VERSIONS)}; apply Supabase migrations "
            "and do not call PostgresSaver.setup() at runtime"
        )


@dataclass(slots=True)
class IngestionCheckpointer:
    """Long-lived PostgresSaver plus the connection pool it borrows.

    Attributes:
        pool: Autocommit pool configured as ``app_checkpointer``.
        saver: LangGraph Postgres checkpointer. ``setup()`` is never invoked.
    """

    pool: ConnectionPool
    saver: PostgresSaver

    def close(self) -> None:
        """Close the underlying connection pool.

        Side Effects:
            Stops accepting new checkpointer connections for this process.
        """

        self.pool.close()


def open_ingestion_checkpointer(
    dsn: str,
    *,
    max_size: int = 4,
) -> IngestionCheckpointer:
    """Open a PostgresSaver against the migrated ``langgraph`` schema.

    Args:
        dsn: Session/direct Postgres URL. Defaults in worker settings to
            ``SUPABASE_DB_URL`` when ``LANGGRAPH_CHECKPOINT_URL`` is unset.
        max_size: Pool ceiling; typically worker concurrency.

    Returns:
        Checkpointer wrapper. Caller must ``close()`` on worker shutdown.

    Raises:
        CheckpointerSchemaError: When migrations 0-9 are not present.

    Side Effects:
        Opens a ``psycopg_pool.ConnectionPool``. Does not auto-migrate.
    """

    pool = ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=max(1, max_size),
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        configure=_configure_checkpointer_connection,
        open=True,
    )
    try:
        with pool.connection() as connection:
            assert_checkpointer_schema_ready(connection)
    except Exception:
        pool.close()
        raise
    saver = PostgresSaver(pool)
    return IngestionCheckpointer(pool=pool, saver=saver)


def compile_ingestion_graph(
    builder: Any,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    interrupt_after: Sequence[str] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile one ingestion ``StateGraph`` with optional durable checkpoints.

    Args:
        builder: Uncompiled ``StateGraph``.
        checkpointer: Optional Postgres (or test) checkpointer. Module-level
            ``langgraph.json`` graphs stay checkpointer-free.
        interrupt_after: Optional node names used only by interrupt/resume tests.

    Returns:
        Compiled graph. Runtime workers pass a PostgresSaver; Studio imports do not.
    """

    kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    if interrupt_after:
        kwargs["interrupt_after"] = list(interrupt_after)
    return builder.compile(**kwargs)  # pyright: ignore[reportUnknownMemberType]
