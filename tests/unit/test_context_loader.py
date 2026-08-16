"""Unit tests for authorized chunk-context batching."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID, uuid4

import pytest
from smart_rag_core.retrieval import context_loader as context_loader_mod
from smart_rag_core.retrieval.context_loader import (
    CONTEXT_BATCH_LIMIT,
    ChunkContext,
    ContextBatchError,
    fetch_authorized_chunk_context,
)
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.unit.typed_attrs import module_attr


class _FetchBatch(Protocol):
    """Private RPC batch helper signature used by the loader tests."""

    def __call__(
        self,
        connection: object,
        *,
        caller: CallerContext,
        chunk_ids: tuple[UUID, ...],
    ) -> tuple[ChunkContext, ...]:
        """Fetch one authorized context batch."""
        ...


def _fetch_context_rpc_batch(
    connection: object,
    *,
    caller: CallerContext,
    chunk_ids: tuple[UUID, ...],
) -> tuple[ChunkContext, ...]:
    """Call the private context RPC helper under test.

    Args:
        connection: Unused connection stand-in.
        caller: Server-derived identity.
        chunk_ids: IDs for one RPC batch.

    Returns:
        Authorized chunk contexts.
    """

    fetch = cast(
        _FetchBatch, module_attr(context_loader_mod, "_fetch_context_rpc_batch")
    )
    return fetch(connection, caller=caller, chunk_ids=chunk_ids)


def _caller() -> CallerContext:
    """Build a member caller for loader tests.

    Returns:
        Frozen caller context.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
        disabled=False,
    )


def test_fetch_context_batches_above_rpc_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fused Hybrid lists may exceed 75 IDs; each RPC stays at the SQL bound."""

    calls: list[int] = []
    chunk_ids = tuple(uuid4() for _ in range(CONTEXT_BATCH_LIMIT + 5))

    def _fake_batch(
        _connection: object,
        *,
        caller: CallerContext,
        chunk_ids: tuple[UUID, ...],
    ) -> tuple[object, ...]:
        """Record RPC batch size without touching Postgres.

        Args:
            _connection: Unused.
            caller: Unused identity.
            chunk_ids: One RPC batch.

        Returns:
            Empty authorized rows.
        """

        del caller
        calls.append(len(chunk_ids))
        return ()

    monkeypatch.setattr(
        "smart_rag_core.retrieval.context_loader._fetch_context_rpc_batch",
        _fake_batch,
    )
    rows = fetch_authorized_chunk_context(
        object(),  # type: ignore[arg-type]
        caller=_caller(),
        chunk_ids=chunk_ids,
    )
    assert rows == ()
    assert calls == [CONTEXT_BATCH_LIMIT, 5]


def test_rpc_batch_rejects_more_than_sql_limit() -> None:
    """A single RPC payload above 75 IDs still fail-closes."""

    oversized = tuple(uuid4() for _ in range(CONTEXT_BATCH_LIMIT + 1))
    with pytest.raises(ContextBatchError, match="context_batch_exceeds_limit"):
        _fetch_context_rpc_batch(
            object(),
            caller=_caller(),
            chunk_ids=oversized,
        )
