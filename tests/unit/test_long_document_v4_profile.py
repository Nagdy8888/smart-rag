"""``hybrid_long_document_v4`` keeps a balanced rerank pool and loads v3."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_LONG_DOCUMENT_V4_PROFILE_SHA256,
    LONG_DOCUMENT_V3_PROFILE_ID,
    LONG_DOCUMENT_V4_PROFILE_ID,
    LONG_DOCUMENT_V4_PROFILE_PATH,
    canonical_profile_digest,
    load_frozen_profile,
)
from smart_rag_core.retrieval.hybrid_run.pool import build_pool_ids
from smart_rag_core.retrieval.types import RetrievalCandidate


def _candidate(chunk_id: UUID, document_id: UUID) -> RetrievalCandidate:
    """Build one fused candidate.

    Args:
        chunk_id: Chunk id.
        document_id: Shared document id.

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


def test_v4_loads_and_v3_still_loads() -> None:
    """v4 is the routed profile and v3 remains a pinned rollback."""

    v4 = load_frozen_profile(LONG_DOCUMENT_V4_PROFILE_ID)
    raw = json.loads(LONG_DOCUMENT_V4_PROFILE_PATH.read_text(encoding="utf-8"))
    assert canonical_profile_digest(raw) == FROZEN_LONG_DOCUMENT_V4_PROFILE_SHA256
    assert v4.dense_head_pin == 10
    assert v4.bm25_head_pin == 5
    assert v4.rollback_profile_id == LONG_DOCUMENT_V3_PROFILE_ID
    assert v4.rerank_pool_size == 20
    v3 = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    assert v3.profile_id == LONG_DOCUMENT_V3_PROFILE_ID
    assert v3.dense_head_pin == 20


def test_fused_rank_outside_dense_head_enters_the_v4_pool() -> None:
    """A fused rank-5 chunk outside the dense top 10 still gets a pool slot."""

    document_id = uuid4()
    dense = [uuid4() for _index in range(12)]
    bm25 = [uuid4() for _index in range(5)]
    gold = uuid4()
    fused_ids = [*bm25, gold, *dense]
    fused = tuple(_candidate(chunk_id, document_id) for chunk_id in fused_ids)
    profile = load_frozen_profile(LONG_DOCUMENT_V4_PROFILE_ID)
    pool, _pins = build_pool_ids(
        query="where is the policy",
        fused=fused,
        fused_ids=fused_ids,
        dense_ids=dense,
        bm25_ids=bm25,
        retrieval_profile=profile,
        supabase_dsn=None,
        open_supabase=lambda: None,
    )
    assert gold in pool
    assert len(pool) <= 20
    outsider = uuid4()
    pool_without, _ignored = build_pool_ids(
        query="where is the policy",
        fused=fused,
        fused_ids=fused_ids,
        dense_ids=[outsider, *dense],
        bm25_ids=[outsider, *bm25],
        retrieval_profile=profile,
        supabase_dsn=None,
        open_supabase=lambda: None,
    )
    assert outsider not in pool_without
