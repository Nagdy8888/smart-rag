"""Unit tests for envelope insert args and vendor status polling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from smart_rag_core.retrieval.graph import (
    GraphIndexEnqueueResult,
    bind_graph_source_text,
    opaque_graph_source_basename,
)
from smart_rag_core.retrieval.lightrag_indexer import (
    GraphIndexerError,
    LightRagGraphIndexer,
)
from smart_rag_core.retrieval.lightrag_qualification import DocumentStatusView

VERSION_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _processed() -> DocumentStatusView:
    return DocumentStatusView(
        document_id=VERSION_ID,
        status="processed",
        track_id="monitor-1",
    )


def test_enqueue_insert_passes_envelope_ids_and_fresh_track() -> None:
    """Vendor insert must use envelope text, version id, unique basename, fresh track."""

    adapter = MagicMock()
    adapter.vendor_document_status = AsyncMock(side_effect=[None, _processed()])
    captured: dict[str, object] = {}

    async def _insert(**kwargs: object) -> GraphIndexEnqueueResult:
        captured.update(kwargs)
        return GraphIndexEnqueueResult(
            document_id=VERSION_ID,
            track_id=str(kwargs["track_id"]),
            status="pending",
        )

    adapter.enqueue_insert = AsyncMock(side_effect=_insert)
    indexer = LightRagGraphIndexer(
        adapter,
        deadline_seconds=1,
        poll_interval_seconds=0.01,
    )
    result = asyncio.run(
        indexer.enqueue_insert(
            document_id=VERSION_ID,
            text="chunk one",
            source_token=opaque_graph_source_basename(VERSION_ID),
            track_id="fresh-monitor-token",
        )
    )
    assert result.status == "processed"
    assert captured["document_id"] == VERSION_ID
    assert captured["source_token"] == f"g-{VERSION_ID}.txt"
    assert captured["track_id"] == "fresh-monitor-token"
    assert captured["track_id"] != VERSION_ID
    assert captured["text"] == "chunk one"
    bound = bind_graph_source_text(
        document_version_id=VERSION_ID,
        normalized_text="chunk one",
    )
    assert VERSION_ID in bound


def test_replay_skips_second_insert_when_already_processed() -> None:
    """Replay of a processed vendor row must not call ainsert again."""

    adapter = MagicMock()
    adapter.vendor_document_status = AsyncMock(return_value=_processed())
    adapter.enqueue_insert = AsyncMock()
    indexer = LightRagGraphIndexer(adapter, deadline_seconds=1)
    result = asyncio.run(
        indexer.enqueue_insert(document_id=VERSION_ID, text="chunk one")
    )
    assert result.status == "processed"
    adapter.enqueue_insert.assert_not_called()


def test_timeout_after_send_polls_existing_row() -> None:
    """Timeout after send must poll the vendor row instead of a duplicate insert."""

    adapter = MagicMock()
    adapter.vendor_document_status = AsyncMock(
        side_effect=[None, _processed(), _processed()]
    )
    adapter.enqueue_insert = AsyncMock(side_effect=TimeoutError())
    indexer = LightRagGraphIndexer(
        adapter,
        deadline_seconds=1,
        poll_interval_seconds=0.01,
    )
    result = asyncio.run(
        indexer.enqueue_insert(document_id=VERSION_ID, text="chunk one")
    )
    assert result.status == "processed"
    assert adapter.enqueue_insert.await_count == 1


def test_failed_vendor_status_raises() -> None:
    """Vendor failed status must not be treated as success."""

    adapter = MagicMock()
    adapter.vendor_document_status = AsyncMock(
        return_value=DocumentStatusView(
            document_id=VERSION_ID,
            status="failed",
        )
    )
    indexer = LightRagGraphIndexer(adapter, deadline_seconds=1)
    with pytest.raises(GraphIndexerError, match="vendor_status_failed"):
        asyncio.run(indexer.enqueue_insert(document_id=VERSION_ID, text="chunk one"))
