"""Channel-phase deadline keeps the rerank reserve (answer-loss repair A5)."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.hybrid_run.assemble import channel_phase_deadline_seconds
from smart_rag_core.retrieval.profiles import (
    CHANNEL_MIN_SECONDS,
    CHANNEL_PHASE_RESERVE_SECONDS,
    RERANK_RESERVED_SECONDS,
    RETRIEVAL_SLICE_SECONDS,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext, UserRole

_Triple = tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]


def _candidate(rank: int) -> RetrievalCandidate:
    """Build one authorized candidate in its own document.

    Args:
        rank: Channel rank.

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


def test_channel_deadline_subtracts_both_reserves() -> None:
    """At the full slice the channel phase ends before both reserves."""

    expected = max(
        CHANNEL_MIN_SECONDS,
        RETRIEVAL_SLICE_SECONDS
        - RERANK_RESERVED_SECONDS
        - CHANNEL_PHASE_RESERVE_SECONDS,
    )
    assert channel_phase_deadline_seconds(RETRIEVAL_SLICE_SECONDS) == expected
    assert CHANNEL_PHASE_RESERVE_SECONDS > 0
    assert expected < RETRIEVAL_SLICE_SECONDS - RERANK_RESERVED_SECONDS


def test_channel_deadline_floor_and_slice_cap() -> None:
    """Short slices get the floor, but never more than the slice itself."""

    assert channel_phase_deadline_seconds(4.0) == CHANNEL_MIN_SECONDS
    assert channel_phase_deadline_seconds(1.0) == 1.0
    assert channel_phase_deadline_seconds(0.0) == 0.0


def test_late_channel_times_out_and_rerank_keeps_its_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake clock jumps by the channel wait; rerank still gets 3 seconds."""

    first, second = _candidate(1), _candidate(2)
    rows = {
        first.chunk_id: _context(first, "annual leave accrues monthly"),
        second.chunk_id: _context(second, "leave carry over rules"),
    }
    now = [1000.0]
    waits: list[float] = []
    remaining_seen: list[float] = []

    def clock() -> float:
        """Return the fake monotonic time.

        Returns:
            Seconds.
        """

        return now[0]

    def fake_parallel(
        jobs: dict[str, Callable[[], object]],
        *,
        deadline_seconds: float,
        durations_ms: dict[str, int] | None = None,
    ) -> tuple[dict[str, object], tuple[str, ...], bool]:
        """Finish dense, let BM25 run past the channel deadline.

        Args:
            jobs: Channel jobs.
            deadline_seconds: Channel wait under test.
            durations_ms: Unused sink.

        Returns:
            Dense completed, BM25 timed out, deadline exhausted.
        """

        del durations_ms
        waits.append(deadline_seconds)
        now[0] += deadline_seconds
        return {"dense": jobs["dense"]()}, ("bm25",), True

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows for the requested IDs.

        Args:
            ids: Requested chunk IDs.

        Returns:
            Matching rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    def rerank(
        _query: str, pool: tuple[RerankPassage, ...], remaining: float
    ) -> _Triple:
        """Record the remaining seconds and return identity rankings.

        Args:
            _query: Unused.
            pool: Authorized pool.
            remaining: Remaining slice seconds at the rerank call.

        Returns:
            Identity rankings with ``none``.
        """

        remaining_seen.append(remaining)
        rankings = tuple(
            RerankRanking(chunk_id=item.candidate.chunk_id, rank=index, support=0.5)
            for index, item in enumerate(pool, start=1)
        )
        usage = RerankUsage(
            request_id="t",
            model="gpt-4o-mini",
            input_tokens=1,
            output_tokens=1,
            model_calls=1,
        )
        return rankings, usage, RerankFallbackReason.NONE

    monkeypatch.setattr(time, "perf_counter", clock)
    monkeypatch.setattr(
        "smart_rag_core.retrieval.hybrid_run.retriever.run_channels_parallel",
        fake_parallel,
    )
    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="hybrid-run")
        ),
        load_context=load,
        rerank=rerank,
    )
    result = retriever.retrieve(
        query="annual leave policy",
        caller=CallerContext(
            user_id=str(uuid4()), role=UserRole.MEMBER, authorization_version=1
        ),
        deadline_seconds=RETRIEVAL_SLICE_SECONDS,
        channel_jobs={
            "dense": lambda: (first, second),
            "bm25": lambda: Bm25RetrievalResult(scanned_ids=(), candidates=()),
        },
    )
    assert waits == [channel_phase_deadline_seconds(RETRIEVAL_SLICE_SECONDS)]
    assert result.deadline_exhausted is True
    assert remaining_seen and remaining_seen[0] >= RERANK_RESERVED_SECONDS
    assert result.rerank_fallback == RerankFallbackReason.NONE.value
