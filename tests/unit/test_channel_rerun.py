"""One channel rerun when the first pass is empty only because of time."""

from __future__ import annotations

import time

from smart_rag_core.retrieval.hybrid_run.channel_rerun import should_rerun_channels
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.types import Bm25RetrievalResult

from tests.unit.test_hybrid_run import (
    sample_caller,
    sample_candidate,
    sample_context,
    sample_retriever,
)


def test_should_rerun_requires_empty_timeout_and_time() -> None:
    """A real empty result, or a short deadline, does not rerun."""

    assert should_rerun_channels(True, True, 18.0) is True
    assert should_rerun_channels(False, True, 30.0) is False
    assert should_rerun_channels(True, False, 30.0) is False
    assert should_rerun_channels(True, True, 17.9) is False


def test_timeout_empty_then_a_hit_reruns_once() -> None:
    """A timed-out empty pass runs again and keeps a single embedding call."""

    dense = sample_candidate(rank=1)
    contexts = {dense.chunk_id: sample_context(dense, text="canonical dense")}
    retriever = sample_retriever(contexts=contexts)
    calls = {"n": 0}

    def flaky() -> object:
        """Hang once, then return the dense candidate.

        Returns:
            Empty on the first call, then one candidate.
        """

        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(0.2)
            return ()
        return (dense,)

    result = retriever.retrieve(
        query="annual leave policy",
        caller=sample_caller(),
        deadline_seconds=0.05,
        remaining_run_seconds=20.0,
        channel_jobs={
            "dense": flaky,
            "bm25": lambda: Bm25RetrievalResult(scanned_ids=(), candidates=()),
        },
    )
    assert calls["n"] == 2
    assert result.embedding_call_count == 1
    assert dense.chunk_id in result.ranked_ids


def test_genuine_empty_and_short_run_do_not_rerun() -> None:
    """No timeout, or too little run time, leaves the channel jobs at one pass."""

    retriever = sample_retriever()
    calls = {"n": 0}

    def empty() -> object:
        """Count one pass and return no rows.

        Returns:
            An empty dense list.
        """

        calls["n"] += 1
        return ()

    result = retriever.retrieve(
        query="annual leave policy",
        caller=sample_caller(),
        deadline_seconds=1.0,
        remaining_run_seconds=30.0,
        channel_jobs={"dense": empty},
    )
    assert calls["n"] == 1
    assert result.fallback_reason is RetrievalFallbackReason.RETRIEVAL_EMPTY

    def hang() -> object:
        """Exceed the slice once.

        Returns:
            Unused empty list.
        """

        calls["n"] += 1
        time.sleep(0.2)
        return ()

    calls["n"] = 0
    retriever.retrieve(
        query="annual leave policy",
        caller=sample_caller(),
        deadline_seconds=0.05,
        remaining_run_seconds=5.0,
        channel_jobs={"dense": hang},
    )
    assert calls["n"] == 1
