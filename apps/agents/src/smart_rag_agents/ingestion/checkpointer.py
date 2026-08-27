"""Postgres checkpointer factory for ingestion graphs.

Pins runtime wiring to ``langgraph-checkpoint-postgres==3.1.2`` on schema
``langgraph`` as role ``app_checkpointer``. Never calls ``PostgresSaver.setup()``;
Phase 2/3 migrations own DDL.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.base import MIGRATIONS
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.typing import ContextT, InputT, OutputT, StateT
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from smart_rag_core.settings.postgres_dsn import require_session_postgres_dsn

CheckpointerConnection: TypeAlias = Connection[DictRow]
CheckpointerPool: TypeAlias = ConnectionPool[CheckpointerConnection]

EXPECTED_CHECKPOINT_VERSIONS: tuple[int, ...] = tuple(range(len(MIGRATIONS)))
"""Official ``PostgresSaver.MIGRATIONS`` indices that must already exist."""


class CheckpointerSchemaError(RuntimeError):
    """Raised when the ``langgraph`` schema does not match the pinned library."""


def configure_checkpointer_connection(connection: CheckpointerConnection) -> None:
    """Bind one pooled connection to the checkpointer role and search path.

    Args:
        connection: Fresh pool connection before first query.

    Side Effects:
        ``SET ROLE app_checkpointer`` and ``SET search_path TO langgraph, pg_catalog``
        so unqualified checkpoint table names hit the Phase 2 schema.
    """

    connection.execute("SET ROLE app_checkpointer")
    connection.execute("SET search_path TO langgraph, pg_catalog")


def _checkpoint_migration_version(row: DictRow) -> int:
    """Read one ``checkpoint_migrations.v`` value from a dict row.

    Args:
        row: ``dict_row`` mapping for ``SELECT v FROM checkpoint_migrations``.

    Returns:
        Integer migration version.

    Raises:
        CheckpointerSchemaError: When ``v`` is missing or not an integer.
    """

    raw: object = row["v"]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CheckpointerSchemaError(
            f"checkpoint_migrations.v is not an integer: {raw!r}"
        )
    return raw


def assert_checkpointer_schema_ready(connection: CheckpointerConnection) -> None:
    """Require checkpoint migration versions to match the pinned library.

    Args:
        connection: Connection already configured for schema ``langgraph``.

    Raises:
        CheckpointerSchemaError: When versions are missing. Callers must apply
            Supabase migrations rather than ``PostgresSaver.setup()``.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT v FROM checkpoint_migrations ORDER BY v")
        versions = tuple(
            _checkpoint_migration_version(row) for row in cursor.fetchall()
        )
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

    pool: CheckpointerPool
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

    Raises:
        ValueError: If ``dsn`` is a known transaction-pooler URL. The
            message never includes the DSN.
    """

    require_session_postgres_dsn(dsn, setting_name="LANGGRAPH_CHECKPOINT_URL")
    pool = ConnectionPool[CheckpointerConnection](
        conninfo=dsn,
        min_size=1,
        max_size=max(1, max_size),
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        configure=configure_checkpointer_connection,
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
    builder: StateGraph[StateT, ContextT, InputT, OutputT],
    *,
    checkpointer: BaseCheckpointSaver[str] | None = None,
    interrupt_after: Sequence[str] | None = None,
) -> CompiledStateGraph[StateT, ContextT, InputT, OutputT]:
    """Compile one ingestion ``StateGraph`` with optional durable checkpoints.

    Args:
        builder: Uncompiled ``StateGraph``.
        checkpointer: Optional Postgres (or test) checkpointer. Module-level
            ``langgraph.json`` graphs stay checkpointer-free.
        interrupt_after: Optional node names used only by interrupt/resume tests.

    Returns:
        Compiled graph. Runtime workers pass a PostgresSaver; Studio imports do not.
    """

    interrupt_nodes = list(interrupt_after) if interrupt_after else None
    return builder.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=checkpointer,
        interrupt_after=interrupt_nodes,
    )
