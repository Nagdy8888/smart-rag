"""``hybrid_long_document_v3``: pin, dense head pin, and dense-first fallback."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

from smart_rag_core.retrieval.context import fallback_pool_order, select_hybrid_context
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.frozen_profile import (
    CANDIDATE_PROFILE_PATH,
    FROZEN_HYBRID_PROFILE_SHA256,
    FROZEN_LONG_DOCUMENT_PROFILE_SHA256,
    FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256,
    FROZEN_PROFILE_PATH,
    LONG_DOCUMENT_PROFILE_ID,
    LONG_DOCUMENT_V3_PROFILE_ID,
    LONG_DOCUMENT_V3_PROFILE_PATH,
    FrozenHybridProfile,
    canonical_profile_digest,
    load_frozen_profile,
    runtime_profile_ids,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.rerank import (
    CHANNEL_HEAD_PIN,
    ContextSelection,
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    channel_head_pins,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

_V2_DIGEST = "1b356c0de0972ee42758f1ef9f0a7a47b283ec779f97fbe9af8f04e490dffd7a"
_V3_DIGEST = "54bf7e76f5eb9e77bbc853296c29c57470f937feb5a5da5be1f4d95f02fea254"
_Triple = tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]
_RerankFn = Callable[[str, tuple[RerankPassage, ...], float], _Triple]


def _digest(path: Path) -> str:
    """Return the canonical digest of one frozen JSON file.

    Args:
        path: Frozen profile path.

    Returns:
        SHA-256 hex of canonical JSON.
    """

    return canonical_profile_digest(json.loads(path.read_text(encoding="utf-8")))


def _candidate(rank: int) -> RetrievalCandidate:
    """Build one authorized candidate in its own document and version.

    Args:
        rank: Fused rank.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=rank,
        channel_score=1.0,
    )


def _context(candidate: RetrievalCandidate, text: str) -> ChunkContext:
    """Build the authorized context row for one candidate.

    Args:
        candidate: Candidate identity.
        text: Canonical text.

    Returns:
        Frozen context row.
    """

    return ChunkContext(
        chunk_id=candidate.chunk_id,
        document_id=candidate.document_id,
        version_id=candidate.version_id,
        parent_chunk_id=None,
        chunk_index=0,
        page_number=1,
        section_path=(),
        token_count=max(1, len(text.split())),
        raw_text=text,
        is_search_representative=True,
    )


def _fused(
    count: int,
) -> tuple[tuple[RetrievalCandidate, ...], tuple[ChunkContext, ...]]:
    """Build fused candidates with distinct texts.

    Args:
        count: Number of candidates.

    Returns:
        Fused candidates and their context rows.
    """

    fused = tuple(_candidate(rank) for rank in range(1, count + 1))
    rows = tuple(
        _context(item, f"passage {index} topic{index}")
        for index, item in enumerate(fused)
    )
    return fused, rows


def _no_parents(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
    """Return no parent rows.

    Args:
        ids: Requested parent IDs.

    Returns:
        Empty tuple.
    """

    del ids
    return ()


def _must_not_run(
    query: str, pool: tuple[RerankPassage, ...], remaining: float
) -> _Triple:
    """Fail when the reserve gate should have skipped rerank.

    Args:
        query: Unused.
        pool: Unused.
        remaining: Unused.

    Raises:
        AssertionError: Always.
    """

    del query, pool, remaining
    raise AssertionError("rerank must not run")


def _failed(query: str, pool: tuple[RerankPassage, ...], remaining: float) -> _Triple:
    """Return a provider failure.

    Args:
        query: Unused.
        pool: Unused.
        remaining: Unused.

    Returns:
        Empty rankings with ``rerank_provider_error``.
    """

    del query, pool, remaining
    return (), None, RerankFallbackReason.PROVIDER_ERROR


def _select(
    fused: tuple[RetrievalCandidate, ...],
    rows: tuple[ChunkContext, ...],
    *,
    retrieval_profile: FrozenHybridProfile | None,
    rerank: _RerankFn,
    remaining: float,
    dense_ids: tuple[UUID, ...],
) -> ContextSelection:
    """Run context selection without a database.

    Args:
        fused: Fused candidates.
        rows: Context rows.
        retrieval_profile: Frozen profile or ``None``.
        rerank: Rerank closure.
        remaining: Remaining slice seconds.
        dense_ids: Dense IDs in rank order.

    Returns:
        The context selection.
    """

    return select_hybrid_context(
        query="policy question",
        profile=None,
        fused=fused,
        contexts=rows,
        channel_hits={},
        rerank=rerank,
        load_context=_no_parents,
        remaining_deadline_seconds=remaining,
        retrieval_profile=retrieval_profile,
        dense_ids=dense_ids,
    )


def test_v3_pin_matches_file_and_new_fields() -> None:
    """The v3 file matches its pin and carries dense pin 20 and dense-first."""

    assert FROZEN_LONG_DOCUMENT_V3_PROFILE_SHA256 == _V3_DIGEST
    assert _digest(LONG_DOCUMENT_V3_PROFILE_PATH) == _V3_DIGEST
    profile = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    assert profile.profile_id == LONG_DOCUMENT_V3_PROFILE_ID
    assert profile.rollback_profile_id == LONG_DOCUMENT_PROFILE_ID
    assert profile.dense_head_pin == 20
    assert profile.fallback_order == "dense_first"
    assert profile.rerank_max_per_document == 20
    assert profile.document_quota == 12
    assert profile.final_token_budget == 6000
    assert {
        LONG_DOCUMENT_V3_PROFILE_ID,
        LONG_DOCUMENT_PROFILE_ID,
    } <= runtime_profile_ids()


def test_default_and_v2_bytes_and_behavior_are_unchanged() -> None:
    """Old digests hold and the new fields default to the old behavior."""

    assert _digest(FROZEN_PROFILE_PATH) == FROZEN_HYBRID_PROFILE_SHA256
    assert _digest(CANDIDATE_PROFILE_PATH) == FROZEN_LONG_DOCUMENT_PROFILE_SHA256
    assert FROZEN_LONG_DOCUMENT_PROFILE_SHA256 == _V2_DIGEST
    for profile_id in (HYBRID_DEFAULT_PROFILE_ID, LONG_DOCUMENT_PROFILE_ID):
        profile = load_frozen_profile(profile_id)
        assert profile.dense_head_pin == CHANNEL_HEAD_PIN
        assert profile.fallback_order == "rrf"


def test_dense_head_pin_twenty_keeps_bm25_at_five() -> None:
    """The dense pin follows the profile; BM25 stays five; ACL bound holds."""

    dense = tuple(uuid4() for _ in range(22))
    bm25 = tuple(uuid4() for _ in range(8))
    fused = dense + bm25
    pins = channel_head_pins(
        dense_ids=dense, bm25_ids=bm25, fused_ids=fused, dense_head=20
    )
    assert pins == dense[:20] + bm25[:CHANNEL_HEAD_PIN]
    default = channel_head_pins(dense_ids=dense, bm25_ids=bm25, fused_ids=fused)
    assert default == dense[:CHANNEL_HEAD_PIN] + bm25[:CHANNEL_HEAD_PIN]
    bounded = channel_head_pins(
        dense_ids=dense, bm25_ids=(), fused_ids=dense[:3], dense_head=20
    )
    assert bounded == dense[:3]


def test_dense_first_moves_dense_rank_one_from_fused_rank_eleven() -> None:
    """Gate skip and failed rerank both put dense rank 1 (fused 11) first."""

    fused, rows = _fused(12)
    dense_ids = (fused[10].chunk_id, fused[2].chunk_id)
    expected = dense_ids + tuple(
        item.chunk_id for index, item in enumerate(fused) if index not in {2, 10}
    )
    v3 = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    gated = _select(
        fused,
        rows,
        retrieval_profile=v3,
        rerank=_must_not_run,
        remaining=1.0,
        dense_ids=dense_ids,
    )
    assert gated.fallback_reason is RerankFallbackReason.TIMEOUT
    assert gated.rerank_order == expected
    assert gated.passages[0].candidate.chunk_id == fused[10].chunk_id
    failed = _select(
        fused,
        rows,
        retrieval_profile=v3,
        rerank=_failed,
        remaining=9.0,
        dense_ids=dense_ids,
    )
    assert failed.fallback_reason is RerankFallbackReason.PROVIDER_ERROR
    assert failed.rerank_order == expected


def test_rrf_fallback_order_is_unchanged_for_v2_and_default() -> None:
    """Profiles without ``dense_first`` keep fused order on fallback."""

    fused, rows = _fused(12)
    fused_order = tuple(item.chunk_id for item in fused)
    v2 = load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    for profile in (v2, None):
        selection = _select(
            fused,
            rows,
            retrieval_profile=profile,
            rerank=_must_not_run,
            remaining=1.0,
            dense_ids=(fused[10].chunk_id,),
        )
        assert selection.rerank_order == fused_order


def test_fallback_pool_order_never_adds_or_drops() -> None:
    """Unknown and repeated dense IDs are ignored; membership is unchanged."""

    pool = tuple(
        RerankPassage(
            candidate=_candidate(rank),
            raw_text=f"p{rank}",
            section_path=(),
            parent_chunk_id=None,
            token_count=1,
            channels=frozenset({"dense"}),
            excerpt=f"p{rank}",
        )
        for rank in range(1, 5)
    )
    v3 = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    last = pool[3].candidate.chunk_id
    ordered = fallback_pool_order(
        pool, retrieval_profile=v3, dense_ids=(uuid4(), last, last)
    )
    assert ordered == (pool[3], pool[0], pool[1], pool[2])
    assert fallback_pool_order(pool, retrieval_profile=v3, dense_ids=()) == pool


def test_partial_ranking_keeps_head_and_orders_tail_by_fallback() -> None:
    """A partial rerank is completed; only its appended tail is reordered."""

    fused, rows = _fused(6)
    dense_ids = (fused[4].chunk_id,)

    def partial(
        query: str, pool: tuple[RerankPassage, ...], remaining: float
    ) -> _Triple:
        """Rank one candidate and append the rest in pool order.

        Args:
            query: Unused.
            pool: Authorized pool.
            remaining: Unused.

        Returns:
            Partial rankings with ``none``.
        """

        del query, remaining
        head = pool[1]
        rest = [item for item in pool if item is not head]
        rankings = [
            RerankRanking(chunk_id=head.candidate.chunk_id, rank=1, support=0.9)
        ]
        rankings.extend(
            RerankRanking(
                chunk_id=item.candidate.chunk_id, rank=index, support=0.0, appended=True
            )
            for index, item in enumerate(rest, start=2)
        )
        usage = RerankUsage(
            request_id="t",
            model="gpt-4o-mini",
            input_tokens=1,
            output_tokens=1,
            model_calls=1,
        )
        return tuple(rankings), usage, RerankFallbackReason.NONE

    ids = [item.chunk_id for item in fused]
    v3 = load_frozen_profile(LONG_DOCUMENT_V3_PROFILE_ID)
    dense_tail = _select(
        fused,
        rows,
        retrieval_profile=v3,
        rerank=partial,
        remaining=9.0,
        dense_ids=dense_ids,
    )
    assert dense_tail.fallback_reason is RerankFallbackReason.NONE
    assert dense_tail.rerank_order == (ids[1], ids[4], ids[0], ids[2], ids[3], ids[5])
    assert dense_tail.rerank_ranked_count == 1
    assert dense_tail.rerank_appended_count == 5
    v2 = load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    fused_tail = _select(
        fused,
        rows,
        retrieval_profile=v2,
        rerank=partial,
        remaining=9.0,
        dense_ids=dense_ids,
    )
    assert fused_tail.rerank_order == (ids[1], ids[0], ids[2], ids[3], ids[4], ids[5])
