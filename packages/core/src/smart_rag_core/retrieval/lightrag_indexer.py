"""Concrete ``GraphIndexer`` using the attached LightRAG runtime adapter.

This module must not import ``lightrag``. Mapping table names and public
ready-status strings are forbidden here. Vendor ``processed`` authorizes
Packet 4 only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from smart_rag_core.jobs.limits import (
    DEFAULT_GRAPH_INDEX_DEADLINE_SECONDS,
    DEFAULT_GRAPH_INDEX_POLL_INTERVAL_SECONDS,
)
from smart_rag_core.retrieval.graph import (
    GraphIndexDeleteResult,
    GraphIndexEnqueueResult,
    GraphIndexer,
    opaque_graph_source_basename,
)
from smart_rag_core.retrieval.lightrag_adapter import LightRagRuntimeAdapter
from smart_rag_core.retrieval.lightrag_qualification import DocumentStatusView

VENDOR_TERMINAL_SUCCESS = "processed"
VENDOR_TERMINAL_FAILURE = "failed"
T = TypeVar("T")


class GraphIndexerError(RuntimeError):
    """Raised when insert, poll, or delete cannot complete safely."""

    def __init__(self, reason: str) -> None:
        """Initialize with a stable machine-readable reason.

        Args:
            reason: Short reason such as ``vendor_status_failed``.
        """

        super().__init__(reason)
        self.reason = reason


async def call_with_one_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    retryable: tuple[type[BaseException], ...] = (
        TimeoutError,
        OSError,
        GraphIndexerError,
    ),
) -> T:
    """Run one async operation with a single application-owned retry.

    Vendor SDK retries stay at zero. The second attempt runs only when the
    first raises a retryable error and the caller still wants a retry.

    Args:
        operation: Zero-argument async callable.
        retryable: Exception types that consume the single retry.

    Returns:
        Result of the first success.

    Raises:
        BaseException: The second failure, or a non-retryable first failure.
    """

    try:
        return await operation()
    except retryable:
        return await operation()


class LightRagGraphIndexer:
    """Application ``GraphIndexer`` bound to one attached runtime adapter."""

    def __init__(
        self,
        adapter: LightRagRuntimeAdapter,
        *,
        deadline_seconds: float = DEFAULT_GRAPH_INDEX_DEADLINE_SECONDS,
        poll_interval_seconds: float = DEFAULT_GRAPH_INDEX_POLL_INTERVAL_SECONDS,
    ) -> None:
        """Bind the attached adapter and poll bounds.

        Args:
            adapter: Runtime adapter from ``open_runtime_lightrag_adapter``.
            deadline_seconds: Maximum time spent polling vendor status.
            poll_interval_seconds: Delay between status polls.
        """

        self._adapter = adapter
        self._deadline_seconds = deadline_seconds
        self._poll_interval_seconds = poll_interval_seconds

    @property
    def adapter(self) -> LightRagRuntimeAdapter:
        """Return the bound runtime adapter."""

        return self._adapter

    async def enqueue_insert(
        self,
        *,
        document_id: str,
        text: str,
        source_token: str | None = None,
        track_id: str | None = None,
    ) -> GraphIndexEnqueueResult:
        """Enqueue normalized version text, then poll until a terminal status.

        Replay first reads vendor status. An existing ``processed`` row skips
        a second ``ainsert``. Timeout after send is not retried as a duplicate
        insert; the indexer polls the existing row instead.

        Args:
            document_id: Canonical document version ID used as vendor ``ids``.
            text: Ordered canonical chunk text for the version.
            source_token: Optional opaque basename. Defaults to
                ``g-{version_id}.txt``.
            track_id: Optional monitoring token. A fresh UUID is used when
                omitted. Never treated as idempotency.

        Returns:
            Monitoring metadata. ``track_id`` is never idempotency.

        Raises:
            GraphIndexerError: On vendor ``failed``, unverifiable status, or
                poll deadline without a terminal row.
        """

        token = source_token or opaque_graph_source_basename(document_id)
        monitor_token = track_id or str(uuid4())
        existing = await self._adapter.vendor_document_status(document_id)
        if existing is not None and existing.status.lower() == VENDOR_TERMINAL_SUCCESS:
            return GraphIndexEnqueueResult(
                document_id=document_id,
                track_id=existing.track_id or monitor_token,
                status=existing.status,
            )
        if existing is not None and existing.status.lower() == VENDOR_TERMINAL_FAILURE:
            raise GraphIndexerError("vendor_status_failed")
        if existing is not None and existing.status.lower() not in {
            "pending",
            "parsing",
            "analyzing",
            "processing",
            "preprocessed",
        }:
            raise GraphIndexerError(f"vendor_status_unverified:{existing.status}")

        if existing is None:
            try:
                enqueued = await self._adapter.enqueue_insert(
                    document_id=document_id,
                    text=text,
                    source_token=token,
                    track_id=monitor_token,
                )
            except (TimeoutError, OSError):
                after_timeout = await self._adapter.vendor_document_status(document_id)
                if after_timeout is None:
                    enqueued = await self._adapter.enqueue_insert(
                        document_id=document_id,
                        text=text,
                        source_token=token,
                        track_id=str(uuid4()),
                    )
                else:
                    enqueued = GraphIndexEnqueueResult(
                        document_id=document_id,
                        track_id=after_timeout.track_id or monitor_token,
                        status=after_timeout.status,
                    )
        else:
            enqueued = GraphIndexEnqueueResult(
                document_id=document_id,
                track_id=existing.track_id or monitor_token,
                status=existing.status,
            )
        terminal = await self.poll_until_terminal(document_id)
        return GraphIndexEnqueueResult(
            document_id=document_id,
            track_id=enqueued.track_id,
            status=terminal.status,
        )

    async def delete_document(
        self,
        *,
        document_id: str,
        delete_llm_cache: bool = True,
    ) -> GraphIndexDeleteResult:
        """Delete one vendor document with a single application retry.

        Args:
            document_id: Canonical document version ID.
            delete_llm_cache: When true, request privacy cache deletion.

        Returns:
            Vendor deletion status.

        Raises:
            GraphIndexerError: If deletion remains unsuccessful after retry.
        """

        async def _once() -> GraphIndexDeleteResult:
            """Issue one vendor delete attempt for this document.

            Returns:
                Vendor deletion status for the current attempt.
            """

            return await self._adapter.delete_document(
                document_id=document_id,
                delete_llm_cache=delete_llm_cache,
            )

        result = await call_with_one_retry(_once)
        if result.status == "fail":
            raise GraphIndexerError("vendor_delete_failed")
        return result

    async def poll_until_terminal(self, document_id: str) -> DocumentStatusView:
        """Poll vendor document status until processed, failed, or deadline.

        Args:
            document_id: Canonical document version ID.

        Returns:
            Terminal status view. ``processed`` does not authorize mapping.

        Raises:
            GraphIndexerError: On missing status, ``failed``, or deadline.
        """

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._deadline_seconds
        last: DocumentStatusView | None = None
        while loop.time() < deadline:
            last = await self._adapter.vendor_document_status(document_id)
            if last is not None:
                lowered = last.status.lower()
                if lowered == VENDOR_TERMINAL_SUCCESS:
                    return last
                if lowered == VENDOR_TERMINAL_FAILURE:
                    raise GraphIndexerError("vendor_status_failed")
            await asyncio.sleep(self._poll_interval_seconds)
        raise GraphIndexerError(
            f"vendor_status_deadline:{last.status if last else 'missing'}"
        )


def as_graph_indexer(indexer: LightRagGraphIndexer) -> GraphIndexer:
    """Return the indexer as the project ``GraphIndexer`` protocol.

    Args:
        indexer: Concrete Packet 3 indexer.

    Returns:
        Protocol-typed indexer for worker imports.
    """

    return indexer
