"""Rerank-pool membership for one Hybrid retrieve.

Pins are reserved first. The remaining slots follow fused rank order, under
the per-document cap. This is the same selection the retriever used inline.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import UUID

from smart_rag_core.retrieval.frozen_profile import FrozenHybridProfile
from smart_rag_core.retrieval.pages import load_chunk_page_numbers
from smart_rag_core.retrieval.profiles import RERANK_MAX_PER_DOCUMENT, RERANK_POOL_SIZE
from smart_rag_core.retrieval.rerank import (
    CHANNEL_HEAD_PIN,
    channel_head_pins,
    merge_rerank_pins,
    named_page_numbers,
    page_head_pins,
    rerank_preload_ids,
)
from smart_rag_core.retrieval.types import RetrievalCandidate


def build_pool_ids(
    *,
    query: str,
    fused: tuple[RetrievalCandidate, ...],
    fused_ids: Sequence[UUID],
    dense_ids: Sequence[UUID],
    bm25_ids: Sequence[UUID],
    retrieval_profile: FrozenHybridProfile | None,
    supabase_dsn: str | None,
    open_supabase: Callable[[], object],
) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
    """Return the chunk IDs that occupy the one-shot rerank pool.

    Args:
        query: User text, used only to detect named page numbers.
        fused: Authorized fused candidates in rank order.
        fused_ids: Chunk IDs of ``fused``, in the same order.
        dense_ids: Dense IDs in channel-rank order.
        bm25_ids: BM25 IDs in channel-rank order.
        retrieval_profile: Frozen profile, or ``None`` for the code defaults.
        supabase_dsn: Canonical DSN. Page pins are skipped when it is absent.
        open_supabase: Opens one short canonical connection for page lookup.

    Returns:
        Pool IDs and the pin IDs reserved inside that pool.

    Side Effects:
        Reads page numbers when the query names a page and a DSN is set.
        A page-lookup failure leaves page pins empty.
    """

    if retrieval_profile is not None:
        pool_size = retrieval_profile.rerank_pool_size
        max_per_document = retrieval_profile.rerank_max_per_document
        dense_head = retrieval_profile.dense_head_pin
        bm25_head = retrieval_profile.bm25_head_pin
    else:
        pool_size = RERANK_POOL_SIZE
        max_per_document = RERANK_MAX_PER_DOCUMENT
        dense_head = CHANNEL_HEAD_PIN
        bm25_head = None
    channel_pins = channel_head_pins(
        dense_ids=dense_ids,
        bm25_ids=bm25_ids,
        fused_ids=fused_ids,
        dense_head=dense_head,
        bm25_head=bm25_head,
    )
    cited_pages = named_page_numbers(query)
    page_pins: tuple[UUID, ...] = ()
    if cited_pages and fused_ids and supabase_dsn:
        try:
            with open_supabase() as page_conn:
                page_by_id = load_chunk_page_numbers(page_conn, chunk_ids=fused_ids)
            page_pins = page_head_pins(
                fused_ids=fused_ids,
                page_by_id=page_by_id,
                pages=cited_pages,
                head=CHANNEL_HEAD_PIN,
            )
        except Exception:
            page_pins = ()
    pinned_ids = merge_rerank_pins(page_pins, channel_pins)
    preload = rerank_preload_ids(
        fused,
        pool_size=pool_size,
        max_per_document=max_per_document,
        pinned_ids=pinned_ids,
    )
    return preload, pinned_ids
