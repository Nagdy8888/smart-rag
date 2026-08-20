"""Unit tests for resumable LightRAG passage batches and transient retry."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from smart_rag_core.gateways.embedding import EmbeddingProviderError
from smart_rag_core.jobs.exceptions import GraphWriterLostError
from smart_rag_core.jobs.graph_source_batches import (
    batch_alert_reasons,
    checkpoint_patch,
    insert_passage_batches,
    is_transient_batch_error,
    parse_processed_source_ids,
    remaining_batches,
)
from smart_rag_core.jobs.limits import GRAPH_SOURCE_INSERT_BATCH_SIZE
from smart_rag_core.retrieval.graph import GraphIndexEnqueueResult
from smart_rag_core.retrieval.lightrag_indexer import (
    GraphIndexerError,
    LightRagGraphIndexer,
)

VERSION = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CHUNK_A = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHUNK_B = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CHUNK_C = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ID_A = f"{VERSION}:{CHUNK_A}"
ID_B = f"{VERSION}:{CHUNK_B}"
ID_C = f"{VERSION}:{CHUNK_C}"


def test_remaining_batches_skip_checkpointed_ids() -> None:
    """Resume must not re-insert sources already checkpointed."""

    batches = remaining_batches(
        texts=("a", "b", "c"),
        document_ids=(ID_A, ID_B, ID_C),
        source_tokens=("g-a.txt", "g-b.txt", "g-c.txt"),
        processed_ids=(ID_A,),
        batch_size=2,
    )
    assert len(batches) == 1
    assert batches[0].document_ids == (ID_B, ID_C)


def test_remaining_batches_reject_oversize_cap() -> None:
    """Batch size above the signed insert cap fails closed."""

    with pytest.raises(GraphIndexerError, match="graph_source_batch_too_large"):
        remaining_batches(
            texts=("a",),
            document_ids=(ID_A,),
            source_tokens=("g-a.txt",),
            processed_ids=(),
            batch_size=GRAPH_SOURCE_INSERT_BATCH_SIZE + 1,
        )


def test_parse_checkpoint_and_patch_round_trip() -> None:
    """Checkpoint JSON must round-trip processed source IDs."""

    patch = checkpoint_patch(
        processed_source_ids=(ID_A, ID_B),
        next_batch_index=1,
        isolate_workspace_key="company_default__rebuild",
    )
    parsed = parse_processed_source_ids(patch)
    assert parsed == (ID_A, ID_B)


def test_timeout_and_429_are_transient() -> None:
    """Provider timeout and HTTP 429 may retry after verified cleanup."""

    assert is_transient_batch_error(TimeoutError("embedding_timeout")) is True
    assert is_transient_batch_error(EmbeddingProviderError("embedding_timeout")) is True
    assert (
        is_transient_batch_error(EmbeddingProviderError("embedding_rate_limited"))
        is True
    )
    assert is_transient_batch_error(GraphIndexerError("vendor_status_failed")) is True
    assert is_transient_batch_error(GraphWriterLostError("job_lease_lost")) is False
    assert is_transient_batch_error(GraphIndexerError("ainsert_source_arity")) is False


def test_batch_alert_reasons_for_latency() -> None:
    """Slow embedding batches emit the latency alert kind."""

    assert "graph_embedding_latency" in batch_alert_reasons(
        batch_size=8, latency_ms=15_000
    )
    assert batch_alert_reasons(batch_size=8, latency_ms=100) == ()


def test_insert_retries_transient_after_cleanup() -> None:
    """A failed batch deletes vendor residue then retries once."""

    adapter = MagicMock()
    indexer = LightRagGraphIndexer(adapter, deadline_seconds=1)
    indexer.enqueue_insert_sources = AsyncMock(
        side_effect=[
            EmbeddingProviderError("embedding_timeout"),
            GraphIndexEnqueueResult(
                document_id=ID_A, track_id="t1", status="processed"
            ),
        ]
    )
    indexer.delete_document = AsyncMock()
    adapter.vendor_document_status = AsyncMock(return_value=None)
    checkpoints: list[dict[str, object]] = []
    result = asyncio.run(
        insert_passage_batches(
            indexer,
            texts=("one",),
            document_ids=(ID_A,),
            source_tokens=("g-a.txt",),
            on_checkpoint=checkpoints.append,
        )
    )
    assert result.status == "processed"
    assert indexer.delete_document.await_count == 1
    assert indexer.enqueue_insert_sources.await_count == 2
    assert checkpoints


def test_insert_stops_on_lease_cancellation() -> None:
    """Worker crash / cancelled lease must not start the next batch."""

    adapter = MagicMock()
    indexer = LightRagGraphIndexer(adapter, deadline_seconds=1)
    indexer.enqueue_insert_sources = AsyncMock(
        return_value=GraphIndexEnqueueResult(
            document_id=ID_A, track_id="t1", status="processed"
        )
    )
    calls = {"n": 0}

    def _lease() -> None:
        """Fail the second lease probe as a cancelled worker.

        Raises:
            GraphWriterLostError: Simulated lease loss after batch one.
        """

        calls["n"] += 1
        if calls["n"] > 2:
            raise GraphWriterLostError("job_lease_lost")

    with pytest.raises(GraphWriterLostError, match="job_lease_lost"):
        asyncio.run(
            insert_passage_batches(
                indexer,
                texts=("one", "two"),
                document_ids=(ID_A, ID_B),
                source_tokens=("g-a.txt", "g-b.txt"),
                batch_size=1,
                on_lease_check=_lease,
            )
        )
    assert indexer.enqueue_insert_sources.await_count == 1


def test_worker_crash_is_not_retried_as_timeout() -> None:
    """Lease loss is not a transient embedding failure."""

    adapter = SimpleNamespace(callbacks=SimpleNamespace(last_embed_latency_ms=0))
    indexer = LightRagGraphIndexer(adapter, deadline_seconds=1)  # type: ignore[arg-type]
    indexer.enqueue_insert_sources = AsyncMock(
        side_effect=GraphWriterLostError("advisory_lock_lost")
    )
    indexer.delete_document = AsyncMock()
    with pytest.raises(GraphWriterLostError, match="advisory_lock_lost"):
        asyncio.run(
            insert_passage_batches(
                indexer,
                texts=("one",),
                document_ids=(ID_A,),
                source_tokens=("g-a.txt",),
            )
        )
    indexer.delete_document.assert_not_called()


def test_unverified_cleanup_blocks_transient_retry() -> None:
    """A leftover vendor row after delete is not a retryable timeout."""

    adapter = MagicMock()
    adapter.vendor_document_status = AsyncMock(
        return_value=SimpleNamespace(status="failed")
    )
    indexer = LightRagGraphIndexer(adapter, deadline_seconds=1)
    indexer.enqueue_insert_sources = AsyncMock(
        side_effect=EmbeddingProviderError("embedding_timeout")
    )
    indexer.delete_document = AsyncMock()
    with pytest.raises(GraphIndexerError, match="vendor_cleanup_unverified"):
        asyncio.run(
            insert_passage_batches(
                indexer,
                texts=("one",),
                document_ids=(ID_A,),
                source_tokens=("g-a.txt",),
            )
        )
    assert indexer.enqueue_insert_sources.await_count == 1


def test_insert_emits_latency_alert() -> None:
    """Embedding wall time at the alert threshold notifies operators."""

    adapter = MagicMock()
    adapter.callbacks = SimpleNamespace(last_embed_latency_ms=15_000)
    adapter.vendor_document_status = AsyncMock(return_value=None)
    indexer = LightRagGraphIndexer(adapter, deadline_seconds=1)
    indexer.enqueue_insert_sources = AsyncMock(
        return_value=GraphIndexEnqueueResult(
            document_id=ID_A, track_id="t1", status="processed"
        )
    )
    alerts: list[tuple[str, int, int]] = []
    asyncio.run(
        insert_passage_batches(
            indexer,
            texts=("one",),
            document_ids=(ID_A,),
            source_tokens=("g-a.txt",),
            on_alert=lambda kind, size, latency_ms: alerts.append(
                (kind, size, latency_ms)
            ),
        )
    )
    assert ("graph_embedding_latency", 1, 15_000) in alerts
