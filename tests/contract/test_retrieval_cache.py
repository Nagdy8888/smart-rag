"""Contract tests for authorization-safe retrieval cache recheck."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest
from smart_rag_core.retrieval.cache_key import hybrid_cache_key
from smart_rag_core.retrieval.cache_store import (
    PROFILE_TTL_SECONDS,
    RESULT_TTL_SECONDS,
    CacheEvent,
    RetrievalCacheStore,
)
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.runtime.valkey import CACHE_KEY_PREFIX, MemoryValkeyClient


def _candidate(chunk_id: UUID) -> RetrievalCandidate:
    """Build one ID-only candidate.

    Args:
        chunk_id: Canonical chunk.

    Returns:
        Candidate with dummy document/version ids.
    """

    return RetrievalCandidate(
        chunk_id=chunk_id,
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def test_cache_ttls_match_packet_defaults() -> None:
    """Result TTL is 30s and profile TTL is 300s."""

    assert RESULT_TTL_SECONDS == 30
    assert PROFILE_TTL_SECONDS == 300


def test_cache_hit_requires_successful_recheck(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A hit is served only after recheck returns the same IDs."""

    caplog.set_level(logging.INFO)
    store = RetrievalCacheStore.in_memory()
    chunk_id = uuid4()
    store.put_results(
        principal_scope_hash="scope-1",
        query_normalized="invoice total",
        visibility_generation=4,
        chunk_ids=(chunk_id,),
        ranks=(1,),
    )

    def recheck(chunk_ids: Sequence[UUID]) -> tuple[RetrievalCandidate, ...]:
        """Keep every cached id.

        Args:
            chunk_ids: Cached ids.

        Returns:
            Matching candidates.
        """

        return tuple(_candidate(item) for item in chunk_ids)

    hit = store.get_results(
        principal_scope_hash="scope-1",
        query_normalized="invoice total",
        visibility_generation=4,
        recheck=recheck,
    )
    assert hit is not None
    assert hit.event is CacheEvent.HIT
    assert hit.chunk_ids == (chunk_id,)
    assert hit.ranks == (1,)
    assert "cache_hit" in caplog.text


def test_recheck_drop_on_acl_delete_or_version_flip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed recheck never serves stale IDs."""

    caplog.set_level(logging.INFO)
    store = RetrievalCacheStore.in_memory()
    cached = uuid4()
    store.put_results(
        principal_scope_hash="scope-1",
        query_normalized="invoice total",
        visibility_generation=4,
        chunk_ids=(cached,),
        ranks=(1,),
    )

    def drop(chunk_ids: Sequence[UUID]) -> tuple[RetrievalCandidate, ...]:
        """Simulate ACL, delete, or current-version flip.

        Args:
            chunk_ids: Cached ids.

        Returns:
            Empty survivors.
        """

        del chunk_ids
        return ()

    dropped = store.get_results(
        principal_scope_hash="scope-1",
        query_normalized="invoice total",
        visibility_generation=4,
        recheck=drop,
    )
    assert dropped is None
    assert "cache_recheck_failed" in caplog.text

    def other(chunk_ids: Sequence[UUID]) -> tuple[RetrievalCandidate, ...]:
        """Return a different id than the cache.

        Args:
            chunk_ids: Cached ids.

        Returns:
            A replacement candidate.
        """

        del chunk_ids
        return (_candidate(uuid4()),)

    flipped = store.get_results(
        principal_scope_hash="scope-1",
        query_normalized="invoice total",
        visibility_generation=4,
        recheck=other,
    )
    assert flipped is None


def test_forbidden_snippet_payload_is_invalidated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cache values may not include passage/snippet/text fields."""

    caplog.set_level(logging.INFO)
    client = MemoryValkeyClient()
    store = RetrievalCacheStore(client)
    digest = hybrid_cache_key(
        principal_scope_hash="scope-1",
        query_normalized="invoice total",
        visibility_generation=4,
    )
    payload = {
        "chunk_ids": [str(uuid4())],
        "ranks": [1],
        "snippet": "full passage must never be cached",
    }
    client.set(
        f"{CACHE_KEY_PREFIX}{digest}",
        json.dumps(payload).encode("utf-8"),
        30,
    )

    def keep(chunk_ids: Sequence[UUID]) -> tuple[RetrievalCandidate, ...]:
        """Would keep IDs if the payload were legal.

        Args:
            chunk_ids: Cached ids.

        Returns:
            Candidates.
        """

        return tuple(_candidate(item) for item in chunk_ids)

    result = store.get_results(
        principal_scope_hash="scope-1",
        query_normalized="invoice total",
        visibility_generation=4,
        recheck=keep,
    )
    assert result is None
    assert client.get(f"{CACHE_KEY_PREFIX}{digest}") is None
    assert "cache_recheck_failed" in caplog.text or "cache_invalidated" in caplog.text


def test_cache_miss_is_emitted(caplog: pytest.LogCaptureFixture) -> None:
    """Unknown keys emit cache_miss and return None."""

    caplog.set_level(logging.INFO)
    store = RetrievalCacheStore.in_memory()

    def unused(chunk_ids: Sequence[UUID]) -> tuple[RetrievalCandidate, ...]:
        """Recheck should not run on a miss.

        Args:
            chunk_ids: Cached ids.

        Returns:
            Empty tuple.
        """

        del chunk_ids
        raise AssertionError("recheck must not run on miss")

    missed = store.get_results(
        principal_scope_hash="missing",
        query_normalized="nope",
        visibility_generation=1,
        recheck=unused,
    )
    assert missed is None
    assert "cache_miss" in caplog.text
