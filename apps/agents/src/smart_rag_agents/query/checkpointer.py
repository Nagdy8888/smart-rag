"""Query-graph Postgres checkpointer that stores compact state only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
)
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from smart_rag_core.memory.summary import compact_query_state
from smart_rag_core.settings.postgres_dsn import require_session_postgres_dsn

from smart_rag_agents.ingestion.checkpointer import (
    EXPECTED_CHECKPOINT_VERSIONS,
    CheckpointerSchemaError,
    IngestionCheckpointer,
    open_ingestion_checkpointer,
)


class CompactPostgresSaver(PostgresSaver):
    """PostgresSaver that hashes source fields before durable writes.

    In-memory graph state may still hold ``citation_text`` for answer
    generation. Checkpoints persist hashes/counts only.
    """

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Persist one compacted checkpoint.

        Args:
            config: LangGraph runnable config including ``thread_id``.
            checkpoint: Channel values to persist.
            metadata: Checkpoint metadata.
            new_versions: Channel versions.

        Returns:
            Config from the inner saver.

        Side Effects:
            Writes compacted checkpoint rows. Never calls ``setup()``.
        """

        return super().put(
            config,
            _compact_checkpoint(checkpoint),
            metadata,
            new_versions,
        )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persist compacted pending writes.

        Args:
            config: Runnable config.
            writes: Channel/value pairs.
            task_id: Task identifier.
            task_path: Optional task path.

        Side Effects:
            Writes compacted blobs. Never calls ``setup()``.
        """

        compacted = tuple(
            (
                channel,
                compact_query_state(cast(Mapping[str, object], value))
                if isinstance(value, Mapping)
                else value,
            )
            for channel, value in writes
        )
        super().put_writes(config, compacted, task_id, task_path)


class CompactAsyncPostgresSaver(AsyncPostgresSaver):
    """Async PostgresSaver that hashes source fields before durable writes.

    Construct only inside a running event loop. ``setup()`` is never called.
    """

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Persist one compacted checkpoint asynchronously.

        Args:
            config: LangGraph runnable config including ``thread_id``.
            checkpoint: Channel values to persist.
            metadata: Checkpoint metadata.
            new_versions: Channel versions.

        Returns:
            Config from the inner saver.

        Side Effects:
            Writes compacted checkpoint rows. Never calls ``setup()``.
        """

        return await super().aput(
            config,
            _compact_checkpoint(checkpoint),
            metadata,
            new_versions,
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Persist compacted pending writes asynchronously.

        Args:
            config: Runnable config.
            writes: Channel/value pairs.
            task_id: Task identifier.
            task_path: Optional task path.

        Side Effects:
            Writes compacted blobs. Never calls ``setup()``.
        """

        compacted = tuple(
            (
                channel,
                compact_query_state(cast(Mapping[str, object], value))
                if isinstance(value, Mapping)
                else value,
            )
            for channel, value in writes
        )
        await super().aput_writes(config, compacted, task_id, task_path)


@dataclass(slots=True)
class QueryAsyncCheckpointer:
    """Long-lived async PostgresSaver plus the pool it borrows.

    Attributes:
        pool: Autocommit async pool configured as ``app_checkpointer``.
        saver: Compact async LangGraph checkpointer. ``setup()`` is never
            invoked.
    """

    pool: AsyncConnectionPool[AsyncConnection[DictRow]]
    saver: CompactAsyncPostgresSaver

    async def aclose(self) -> None:
        """Close the underlying async connection pool.

        Side Effects:
            Stops accepting new checkpointer connections for this process.
        """

        await self.pool.close()


QUERY_CHECKPOINTER_POOL_MAX_SIZE = 8
"""Default pool size. Signed envelope allows five concurrent query runs."""


def open_query_checkpointer(
    dsn: str, *, max_size: int = QUERY_CHECKPOINTER_POOL_MAX_SIZE
) -> IngestionCheckpointer:
    """Open a compacting PostgresSaver on the migrated ``langgraph`` schema.

    Args:
        dsn: Session/direct Postgres URL.
        max_size: Pool ceiling. Default 8 covers the signed five concurrent
            query runs with headroom. No dedicated settings field exists.

    Returns:
        Wrapper whose ``saver`` hashes source fields on write.

    Raises:
        CheckpointerSchemaError: When checkpoint migrations are missing.

    Side Effects:
        Opens a connection pool. Never calls ``PostgresSaver.setup()``.
    """

    opened = open_ingestion_checkpointer(dsn, max_size=max_size)
    compact = CompactPostgresSaver(opened.pool)
    return IngestionCheckpointer(pool=opened.pool, saver=compact)


async def _configure_async_checkpointer_connection(
    connection: AsyncConnection[DictRow],
) -> None:
    """Bind one async pooled connection to the checkpointer role.

    Args:
        connection: Fresh pool connection before first query.

    Side Effects:
        ``SET ROLE app_checkpointer`` and ``SET search_path TO langgraph,
        pg_catalog``.
    """

    await connection.execute("SET ROLE app_checkpointer")
    await connection.execute("SET search_path TO langgraph, pg_catalog")


def _async_checkpoint_migration_version(row: DictRow) -> int:
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


async def _assert_async_checkpointer_schema_ready(
    connection: AsyncConnection[DictRow],
) -> None:
    """Require checkpoint migration versions to match the pinned library.

    Args:
        connection: Connection already configured for schema ``langgraph``.

    Raises:
        CheckpointerSchemaError: When versions are missing. Callers must
            apply Supabase migrations rather than ``AsyncPostgresSaver.setup()``.
    """

    async with connection.cursor() as cursor:
        await cursor.execute("SELECT v FROM checkpoint_migrations ORDER BY v")
        rows = await cursor.fetchall()
    versions = tuple(_async_checkpoint_migration_version(row) for row in rows)
    if versions != EXPECTED_CHECKPOINT_VERSIONS:
        raise CheckpointerSchemaError(
            "langgraph checkpoint schema versions "
            f"{list(versions)} do not match pinned "
            f"langgraph-checkpoint-postgres migrations "
            f"{list(EXPECTED_CHECKPOINT_VERSIONS)}; apply Supabase migrations "
            "and do not call AsyncPostgresSaver.setup() at runtime"
        )


async def open_query_async_checkpointer(
    dsn: str, *, max_size: int = QUERY_CHECKPOINTER_POOL_MAX_SIZE
) -> QueryAsyncCheckpointer:
    """Open a compacting ``AsyncPostgresSaver`` on the migrated schema.

    Must be awaited from a running event loop. The saver constructor
    captures that loop.

    Args:
        dsn: Session/direct Postgres URL.
        max_size: Pool ceiling. Default 8 covers the signed five concurrent
            query runs with headroom.

    Returns:
        Wrapper whose ``saver`` hashes source fields on async write.

    Raises:
        CheckpointerSchemaError: When checkpoint migrations are missing.
        ValueError: If ``dsn`` is a known transaction-pooler URL. The
            message never includes the DSN.

    Side Effects:
        Opens an async connection pool. Never calls
        ``AsyncPostgresSaver.setup()``.
    """

    require_session_postgres_dsn(dsn, setting_name="LANGGRAPH_CHECKPOINT_URL")
    pool = AsyncConnectionPool[AsyncConnection[DictRow]](
        conninfo=dsn,
        min_size=1,
        max_size=max(1, max_size),
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        configure=_configure_async_checkpointer_connection,
        open=False,
    )
    await pool.open()
    try:
        async with pool.connection() as connection:
            await _assert_async_checkpointer_schema_ready(connection)
        saver = CompactAsyncPostgresSaver(pool)
    except Exception:
        await pool.close()
        raise
    return QueryAsyncCheckpointer(pool=pool, saver=saver)


def probe_query_checkpoint_runtime(dsn: str, *, timeout_seconds: int = 1) -> None:
    """Open the pinned saver and store on one bounded connection, then close.

    Args:
        dsn: Session/direct Postgres URL.
        timeout_seconds: libpq connect timeout in seconds.

    Raises:
        ValueError: If ``dsn`` is a known transaction-pooler URL. The
            message never includes the DSN.
        Exception: Connection, role, or schema failure. Callers must not
            log exception text that might include the DSN.

    Side Effects:
        Opens one autocommit connection, applies ``app_checkpointer`` and
        ``langgraph`` search_path, constructs ``PostgresSaver`` and
        ``PostgresStore`` without ``setup()``, then closes.
    """

    import psycopg
    from langgraph.store.postgres import PostgresStore
    from psycopg.rows import dict_row
    from smart_rag_core.settings.postgres_dsn import require_session_postgres_dsn

    from smart_rag_agents.ingestion.checkpointer import (
        _configure_checkpointer_connection,
    )

    require_session_postgres_dsn(dsn, setting_name="LANGGRAPH_CHECKPOINT_URL")
    with psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=max(1, timeout_seconds),
        prepare_threshold=0,
        row_factory=dict_row,
    ) as connection:
        _configure_checkpointer_connection(connection)
        saver = PostgresSaver(connection)
        store = PostgresStore(conn=connection)
        connection.execute("SELECT 1")
        if saver is None or store is None:
            raise RuntimeError("langgraph runtime probe failed")


def _compact_checkpoint(checkpoint: Checkpoint) -> Checkpoint:
    """Copy a checkpoint and hash nested source-document fields.

    Args:
        checkpoint: LangGraph checkpoint mapping.

    Returns:
        Checkpoint whose ``channel_values`` are compacted.
    """

    copied = dict(checkpoint)
    values = copied.get("channel_values")
    if isinstance(values, Mapping):
        copied["channel_values"] = compact_query_state(
            cast(Mapping[str, object], values)
        )
    return cast(Checkpoint, copied)
