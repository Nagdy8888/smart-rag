"""ACL-safe Hybrid retrieve-path cache hits, misses, and outages."""

from __future__ import annotations

from uuid import UUID, uuid4

from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
from smart_rag_core.retrieval.cache_store import RetrievalCacheStore
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.profiles import RetrievalFallbackReason
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.runtime.valkey import MemoryValkeyClient
from smart_rag_core.security.identity import CallerContext, UserRole


def _caller() -> CallerContext:
    """Build a server-derived caller.

    Returns:
        Frozen caller context.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _candidate() -> RetrievalCandidate:
    """Build one authorized candidate.

    Returns:
        Frozen candidate.
    """

    ident = uuid4()
    return RetrievalCandidate(
        chunk_id=ident,
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def _context(candidate: RetrievalCandidate) -> ChunkContext:
    """Build one authorized context row.

    Args:
        candidate: Candidate identity.

    Returns:
        Canonical context without BM25 text.
    """

    return ChunkContext(
        chunk_id=candidate.chunk_id,
        document_id=candidate.document_id,
        version_id=candidate.version_id,
        parent_chunk_id=None,
        chunk_index=0,
        page_number=2,
        section_path=("Leave",),
        token_count=4,
        raw_text="canonical leave policy",
        is_search_representative=True,
    )


def test_identical_query_hits_cache_without_channels() -> None:
    """A second identical query can reuse rechecked IDs."""

    item = _candidate()
    rows = {item.chunk_id: _context(item)}
    store = RetrievalCacheStore.in_memory()
    ran = {"value": 0}

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows.

        Args:
            ids: Requested IDs.

        Returns:
            Matching context rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    def job() -> object:
        """Count channel invocations.

        Returns:
            One dense candidate.
        """

        ran["value"] += 1
        return (item,)

    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="cache-hit")
        ),
        load_context=load,
        retrieval_cache=store,
    )
    caller = _caller()
    first = retriever.retrieve(
        query="annual leave policy",
        caller=caller,
        channel_jobs={"dense": job},
    )
    assert item.chunk_id in first.ranked_ids
    assert ran["value"] == 1
    second = retriever.retrieve(
        query="annual leave policy",
        caller=caller,
        channel_jobs={"dense": job},
    )
    assert second.ranked_ids == first.ranked_ids
    assert second.embedding_call_count == 0
    assert ran["value"] == 1
    assert "bm25 snippet" not in " ".join(
        unit.citation_text for unit in second.evidence
    )


def test_cold_bypass_skips_warm_cache_and_reruns_channels() -> None:
    """Exam cache_mode skips ID/rank cache get/put without cloning ranking."""

    from smart_rag_core.retrieval.cache_store import RetrievalCacheMode

    item = _candidate()
    rows = {item.chunk_id: _context(item)}
    store = RetrievalCacheStore.in_memory()
    ran = {"value": 0}

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows.

        Args:
            ids: Requested IDs.

        Returns:
            Matching context rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    def job() -> object:
        """Count channel invocations.

        Returns:
            One dense candidate.
        """

        ran["value"] += 1
        return (item,)

    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="cache-bypass")
        ),
        load_context=load,
        retrieval_cache=store,
    )
    caller = _caller()
    first = retriever.retrieve(
        query="annual leave policy",
        caller=caller,
        channel_jobs={"dense": job},
    )
    assert ran["value"] == 1
    bypassed = retriever.retrieve(
        query="annual leave policy",
        caller=caller,
        channel_jobs={"dense": job},
        cache_mode=RetrievalCacheMode.COLD_BYPASS,
    )
    assert bypassed.ranked_ids == first.ranked_ids
    assert bypassed.embedding_call_count == 1
    assert ran["value"] == 2


def test_acl_downgrade_does_not_serve_stale_ids() -> None:
    """Unauthorized cached IDs are dropped by recheck and do not become evidence."""

    item = _candidate()
    rows = {item.chunk_id: _context(item)}
    store = RetrievalCacheStore.in_memory()
    allowed = {"value": True}

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows only while allowed.

        Args:
            ids: Requested IDs.

        Returns:
            Matching context rows, or empty after ACL downgrade.
        """

        if not allowed["value"]:
            return ()
        return tuple(rows[item] for item in ids if item in rows)

    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="cache-acl")
        ),
        load_context=load,
        retrieval_cache=store,
    )
    caller = _caller()
    first = retriever.retrieve(
        query="annual leave policy",
        caller=caller,
        channel_jobs={"dense": lambda: (item,)},
    )
    assert item.chunk_id in first.ranked_ids
    allowed["value"] = False
    second = retriever.retrieve(
        query="annual leave policy",
        caller=caller,
        channel_jobs={"dense": lambda: ()},
    )
    assert item.chunk_id not in second.ranked_ids
    assert second.evidence == ()


def test_cache_outage_is_a_miss() -> None:
    """Valkey outage does not fail the query."""

    item = _candidate()
    rows = {item.chunk_id: _context(item)}
    client = MemoryValkeyClient(fail_closed=True)
    store = RetrievalCacheStore(client)

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows.

        Args:
            ids: Requested IDs.

        Returns:
            Matching context rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="cache-outage")
        ),
        load_context=load,
        retrieval_cache=store,
    )
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={"dense": lambda: (item,)},
    )
    assert result.fallback_reason is RetrievalFallbackReason.NONE
    assert item.chunk_id in result.ranked_ids
    assert result.embedding_call_count == 1
