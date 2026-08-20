"""Bounded, resumable canonical-passage LightRAG insert batches.

One 164-source ``ainsert`` is forbidden. LightRAG 1.5.6 cancels remaining
list items when a single embedding flush is force-killed. Small batches plus
durable checkpoints keep already-processed sources.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from smart_rag_core.gateways.embedding import EmbeddingProviderError
from smart_rag_core.jobs.limits import (
    GRAPH_EMBEDDING_LATENCY_ALERT_MS,
    GRAPH_SOURCE_BATCH_SIZE_ALERT,
    GRAPH_SOURCE_BATCH_TRANSIENT_ATTEMPTS,
    GRAPH_SOURCE_INSERT_BATCH_SIZE,
)
from smart_rag_core.retrieval.graph import GraphIndexEnqueueResult
from smart_rag_core.retrieval.lightrag_indexer import (
    GraphIndexerError,
    LightRagGraphIndexer,
)

CHECKPOINT_PAYLOAD_KEY = "source_batch_checkpoint"
TRANSIENT_BATCH_REASONS = frozenset(
    {
        "embedding_timeout",
        "embedding_rate_limited",
        "vendor_status_failed",
    }
)


@dataclass(frozen=True, slots=True)
class PassageBatch:
    """One bounded ``ainsert`` slice.

    Attributes:
        index: Zero-based batch index in the remaining stream.
        texts: Envelope-bound passage texts.
        document_ids: Deterministic ``{version_id}:{chunk_id}`` source IDs.
        source_tokens: Opaque basenames, 1:1 with ``document_ids``.
    """

    index: int
    texts: tuple[str, ...]
    document_ids: tuple[str, ...]
    source_tokens: tuple[str, ...]


def parse_processed_source_ids(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Return checkpointed source IDs from a job payload.

    Args:
        payload: ``lightrag_index_jobs.payload_ref``.

    Returns:
        Previously completed source IDs, or empty when no checkpoint exists.
    """

    raw = payload.get(CHECKPOINT_PAYLOAD_KEY)
    if not isinstance(raw, Mapping):
        return ()
    ids = raw.get("processed_source_ids")
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        return ()
    return tuple(str(item) for item in ids if str(item).strip())


def remaining_batches(
    *,
    texts: tuple[str, ...],
    document_ids: tuple[str, ...],
    source_tokens: tuple[str, ...],
    processed_ids: Sequence[str],
    batch_size: int = GRAPH_SOURCE_INSERT_BATCH_SIZE,
) -> tuple[PassageBatch, ...]:
    """Slice unprocessed sources into bounded insert batches.

    Args:
        texts: Envelope-bound passage texts, 1:1 with IDs.
        document_ids: Deterministic source IDs.
        source_tokens: Opaque basenames, 1:1 with IDs.
        processed_ids: Checkpointed source IDs to skip.
        batch_size: Maximum sources per ``ainsert``. Must stay at or below
            ``GRAPH_SOURCE_INSERT_BATCH_SIZE``.

    Returns:
        Remaining batches in canonical order.

    Raises:
        GraphIndexerError: On arity errors or an oversized batch size.
    """

    if not (len(texts) == len(document_ids) == len(source_tokens) and texts):
        raise GraphIndexerError("ainsert_source_arity")
    if batch_size < 1 or batch_size > GRAPH_SOURCE_INSERT_BATCH_SIZE:
        raise GraphIndexerError("graph_source_batch_too_large")
    done = set(processed_ids)
    pending_indexes = [
        index
        for index, document_id in enumerate(document_ids)
        if document_id not in done
    ]
    batches: list[PassageBatch] = []
    for offset in range(0, len(pending_indexes), batch_size):
        slice_indexes = pending_indexes[offset : offset + batch_size]
        batches.append(
            PassageBatch(
                index=len(batches),
                texts=tuple(texts[index] for index in slice_indexes),
                document_ids=tuple(document_ids[index] for index in slice_indexes),
                source_tokens=tuple(source_tokens[index] for index in slice_indexes),
            )
        )
    return tuple(batches)


def checkpoint_patch(
    *,
    processed_source_ids: tuple[str, ...],
    next_batch_index: int,
    isolate_workspace_key: str | None,
) -> dict[str, object]:
    """Build the JSON merge written after a successful batch.

    Args:
        processed_source_ids: All source IDs finished so far, including this
            batch.
        next_batch_index: Index of the following remaining batch.
        isolate_workspace_key: Candidate workspace when isolating, else
            ``None``.

    Returns:
        Payload fragment merged into ``payload_ref``.
    """

    body: dict[str, object] = {
        "processed_source_ids": list(processed_source_ids),
        "next_batch_index": next_batch_index,
    }
    if isolate_workspace_key is not None:
        body["isolate_workspace_key"] = isolate_workspace_key
    return {CHECKPOINT_PAYLOAD_KEY: body}


def is_transient_batch_error(error: BaseException) -> bool:
    """Return whether a batch failure may retry after verified cleanup.

    Args:
        error: Exception raised by insert, poll, or the embedding gateway.

    Returns:
        True for provider timeout, HTTP 429, and vendor ``failed`` after an
        aborted batch. Lease loss is not transient.
    """

    if isinstance(error, TimeoutError):
        return True
    if isinstance(error, EmbeddingProviderError):
        return error.reason in TRANSIENT_BATCH_REASONS
    if isinstance(error, GraphIndexerError):
        return error.reason in TRANSIENT_BATCH_REASONS
    reason = getattr(error, "reason", "")
    return str(reason) in TRANSIENT_BATCH_REASONS


def batch_alert_reasons(
    *,
    batch_size: int,
    latency_ms: int,
) -> tuple[str, ...]:
    """Return alert kinds for an oversized or slow embedding/insert batch.

    Args:
        batch_size: Sources in the current ``ainsert`` or embed call.
        latency_ms: Last embedding wall time in milliseconds.

    Returns:
        Zero or more kind tokens: ``graph_source_batch_size`` and/or
        ``graph_embedding_latency``.
    """

    kinds: list[str] = []
    if batch_size > GRAPH_SOURCE_BATCH_SIZE_ALERT:
        kinds.append("graph_source_batch_size")
    if latency_ms >= GRAPH_EMBEDDING_LATENCY_ALERT_MS:
        kinds.append("graph_embedding_latency")
    return tuple(kinds)


async def insert_passage_batches(
    indexer: LightRagGraphIndexer,
    *,
    texts: tuple[str, ...],
    document_ids: tuple[str, ...],
    source_tokens: tuple[str, ...],
    processed_ids: Sequence[str] = (),
    batch_size: int = GRAPH_SOURCE_INSERT_BATCH_SIZE,
    transient_attempts: int = GRAPH_SOURCE_BATCH_TRANSIENT_ATTEMPTS,
    isolate_workspace_key: str | None = None,
    on_lease_check: Callable[[], None] | None = None,
    on_checkpoint: Callable[[dict[str, object]], None] | None = None,
    on_alert: Callable[[str, int, int], None] | None = None,
) -> GraphIndexEnqueueResult:
    """Insert remaining passage sources in small resumable batches.

    Args:
        indexer: Application GraphIndexer bound to the candidate or live
            workspace.
        texts: Envelope-bound passage texts, 1:1 with IDs.
        document_ids: Deterministic source IDs.
        source_tokens: Opaque basenames, 1:1 with IDs.
        processed_ids: Checkpointed source IDs to skip.
        batch_size: Maximum sources per ``ainsert``.
        transient_attempts: First try plus retries after verified cleanup.
        isolate_workspace_key: Candidate workspace recorded in checkpoints.
        on_lease_check: Cooperative lock/lease probe before each attempt.
        on_checkpoint: Persist processed IDs after a successful batch.
        on_alert: Optional ``(kind, batch_size, latency_ms)`` operator hook.

    Returns:
        Last batch enqueue result. ``processed`` does not authorize mapping.

    Raises:
        GraphIndexerError: Permanent vendor failure, arity error, or
            exhausted transient retries.
        EmbeddingProviderError: Permanent provider failure after retries.

    Side Effects:
        May ``ainsert`` and ``adelete_by_doc_id`` for a failed batch before
        retry. Checkpoints are the caller's durable write.
    """

    finished = list(processed_ids)
    last = GraphIndexEnqueueResult(
        document_id=document_ids[0],
        track_id=str(uuid4()),
        status="pending",
    )
    batches = remaining_batches(
        texts=texts,
        document_ids=document_ids,
        source_tokens=source_tokens,
        processed_ids=finished,
        batch_size=batch_size,
    )
    if not batches:
        return GraphIndexEnqueueResult(
            document_id=document_ids[0],
            track_id=last.track_id,
            status="processed",
        )
    for batch in batches:
        if on_lease_check is not None:
            on_lease_check()
        if on_alert is not None:
            for kind in batch_alert_reasons(
                batch_size=len(batch.document_ids), latency_ms=0
            ):
                on_alert(kind, len(batch.document_ids), 0)
        last = await _insert_batch_with_transient_retry(
            indexer,
            batch=batch,
            attempts=transient_attempts,
            on_lease_check=on_lease_check,
            on_alert=on_alert,
        )
        finished.extend(batch.document_ids)
        if on_checkpoint is not None:
            on_checkpoint(
                checkpoint_patch(
                    processed_source_ids=tuple(dict.fromkeys(finished)),
                    next_batch_index=batch.index + 1,
                    isolate_workspace_key=isolate_workspace_key,
                )
            )
    return last


async def _insert_batch_with_transient_retry(
    indexer: LightRagGraphIndexer,
    *,
    batch: PassageBatch,
    attempts: int,
    on_lease_check: Callable[[], None] | None,
    on_alert: Callable[[str, int, int], None] | None,
) -> GraphIndexEnqueueResult:
    """Insert one batch, cleaning vendor residue before a transient retry.

    Args:
        indexer: Bound GraphIndexer.
        batch: Sources for this ``ainsert``.
        attempts: Maximum tries including the first.
        on_lease_check: Cooperative lock/lease probe.
        on_alert: Optional latency alert hook after the attempt.

    Returns:
        Terminal enqueue result for this batch.

    Raises:
        BaseException: The last non-retryable or exhausted failure.
    """

    last_error: BaseException | None = None
    for attempt in range(max(1, attempts)):
        if on_lease_check is not None:
            on_lease_check()
        try:
            result = await indexer.enqueue_insert_sources(
                texts=batch.texts,
                document_ids=batch.document_ids,
                source_tokens=batch.source_tokens,
            )
            _emit_embed_alerts(
                indexer,
                on_alert=on_alert,
                batch_size=len(batch.document_ids),
            )
            return result
        except BaseException as error:
            last_error = error
            _emit_embed_alerts(
                indexer,
                on_alert=on_alert,
                batch_size=len(batch.document_ids),
            )
            if attempt + 1 >= attempts or not is_transient_batch_error(error):
                raise
            await _cleanup_batch_sources(indexer, document_ids=batch.document_ids)
    if last_error is not None:
        raise last_error
    raise GraphIndexerError("vendor_status_failed")


def _emit_embed_alerts(
    indexer: LightRagGraphIndexer,
    *,
    on_alert: Callable[[str, int, int], None] | None,
    batch_size: int,
) -> None:
    """Emit latency alerts from the last embedding callback when present.

    Args:
        indexer: Indexer whose adapter callbacks record embed latency.
        on_alert: Optional operator hook.
        batch_size: Current insert batch size.
    """

    if on_alert is None:
        return
    callbacks = getattr(indexer.adapter, "callbacks", None)
    latency_ms = int(getattr(callbacks, "last_embed_latency_ms", 0) or 0)
    for kind in batch_alert_reasons(batch_size=batch_size, latency_ms=latency_ms):
        on_alert(kind, batch_size, latency_ms)


async def _cleanup_batch_sources(
    indexer: LightRagGraphIndexer,
    *,
    document_ids: tuple[str, ...],
) -> None:
    """Delete vendor rows for a failed batch before retry.

    Args:
        indexer: Bound GraphIndexer.
        document_ids: Source IDs inserted or aborted in this batch.

    Raises:
        GraphIndexerError: If a delete remains unsuccessful or a vendor
            status row still exists after delete.

    Side Effects:
        One ``adelete_by_doc_id`` per source, with LLM-cache deletion.
        Insert retry is forbidden until every source status is gone.
    """

    for document_id in document_ids:
        await indexer.delete_document(document_id=document_id, delete_llm_cache=True)
        status_fn = getattr(
            getattr(indexer, "adapter", None),
            "vendor_document_status",
            None,
        )
        if not callable(status_fn):
            raise GraphIndexerError("vendor_cleanup_unverified")
        remaining = await status_fn(document_id)
        if remaining is not None:
            raise GraphIndexerError("vendor_cleanup_unverified")
