"""``hybrid_long_document_v5`` widens the rerank pool and keeps the per-document cap."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_LONG_DOCUMENT_V5_PROFILE_SHA256,
    LONG_DOCUMENT_V4_PROFILE_ID,
    LONG_DOCUMENT_V5_PROFILE_ID,
    LONG_DOCUMENT_V5_PROFILE_PATH,
    canonical_profile_digest,
    load_frozen_profile,
)
from smart_rag_core.retrieval.hybrid_run.pool import build_pool_ids
from smart_rag_core.retrieval.types import RetrievalCandidate


def _candidate(chunk_id: UUID, document_id: UUID) -> RetrievalCandidate:
    """Build one fused candidate.

    Args:
        chunk_id: Chunk id.
        document_id: Document that owns the chunk.

    Returns:
        A zero-score candidate.
    """

    return RetrievalCandidate(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=document_id,
        channel_rank=1,
        channel_score=0.0,
    )


def test_v5_loads_and_v4_still_loads() -> None:
    """v5 is the routed profile. v4 stays pinned with the pool of 20."""

    v5 = load_frozen_profile(LONG_DOCUMENT_V5_PROFILE_ID)
    raw = json.loads(LONG_DOCUMENT_V5_PROFILE_PATH.read_text(encoding="utf-8"))
    assert canonical_profile_digest(raw) == FROZEN_LONG_DOCUMENT_V5_PROFILE_SHA256
    assert v5.rerank_pool_size == 60
    assert v5.rerank_max_per_document == 20
    assert v5.dense_head_pin == 10
    assert v5.bm25_head_pin == 5
    assert v5.rollback_profile_id == LONG_DOCUMENT_V4_PROFILE_ID
    v4 = load_frozen_profile(LONG_DOCUMENT_V4_PROFILE_ID)
    assert v4.rerank_pool_size == 20


def test_later_fused_rank_from_another_document_enters_the_v5_pool() -> None:
    """A fused rank past 20 from a second document enters the pool of 60.

    The first document still stops at the per-document cap of 20.
    """

    first = uuid4()
    second = uuid4()
    first_ids = [uuid4() for _index in range(31)]
    later = uuid4()
    fused_ids = [*first_ids, later]
    fused = tuple(
        _candidate(chunk_id, first if chunk_id != later else second)
        for chunk_id in fused_ids
    )
    profile = load_frozen_profile(LONG_DOCUMENT_V5_PROFILE_ID)
    pool, _pins = build_pool_ids(
        query="where is the policy",
        fused=fused,
        fused_ids=fused_ids,
        dense_ids=first_ids[:10],
        bm25_ids=first_ids[:5],
        retrieval_profile=profile,
        supabase_dsn=None,
        open_supabase=lambda: None,
    )
    assert later in pool
    assert first_ids[30] not in pool
    assert len(pool) <= 60
