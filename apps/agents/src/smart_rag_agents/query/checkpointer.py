"""Query-graph Postgres checkpointer that stores compact state only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
)
from langgraph.checkpoint.postgres import PostgresSaver
from smart_rag_core.memory.summary import compact_query_state

from smart_rag_agents.ingestion.checkpointer import (
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
