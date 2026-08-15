"""Unit tests for Packet 9 Wave 1A HybridRetriever composition."""

from __future__ import annotations

import time
from uuid import UUID, uuid4

import pytest
from smart_rag_core.evaluation.schema import det
from smart_rag_core.gateways.embedding import (
    EmbeddingGateway,
    EmbeddingRequest,
    MockEmbeddingAdapter,
)
from smart_rag_core.query_profile.profiler import profile_query_sync
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    heading_inventory_from_contexts,
    locators_from_provenance,
)
from smart_rag_core.retrieval.hybrid import assemble_hybrid
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.profiles import (
    BM25_AUTHORIZED_SURVIVOR_CAP,
    DENSE_CANDIDATE_CAP,
    FINAL_EVIDENCE_MAX,
    MAX_NORMALIZED_QUERY_CHARS,
    RETRIEVAL_SLICE_SECONDS,
    TERM_CANDIDATE_CAP,
    DenseMode,
    RetrievalFallbackReason,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.retrieval.types import (
    Bm25RetrievalResult,
    DenseRetrievalResult,
    RetrievalCandidate,
    TermRetrievalResult,
)
from smart_rag_core.security.identity import CallerContext, UserRole

BM25_SNIPPET = "bm25 snippet must never be cited"


def _caller(*, disabled: bool = False) -> CallerContext:
    """Build a server-derived caller for retrieve tests.

    Args:
        disabled: Whether the profile is disabled.

    Returns:
        Frozen caller context.
    """

    return CallerContext(
        user_id=str(uuid4()),
        role=UserRole.MEMBER,
        authorization_version=1,
        disabled=disabled,
    )


def _candidate(*, rank: int = 1, chunk: UUID | None = None) -> RetrievalCandidate:
    """Build one synthetic authorized candidate.

    Args:
        rank: Channel rank.
        chunk: Optional chunk id.

    Returns:
        Frozen candidate.
    """

    ident = chunk or uuid4()
    return RetrievalCandidate(
        chunk_id=ident,
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=rank,
        channel_score=1.0,
    )


def _context(
    candidate: RetrievalCandidate,
    *,
    text: str,
    page: int | None = 2,
    section: tuple[str, ...] = ("Leave", "Policy"),
    sheet_name: str | None = None,
    range_ref: str | None = None,
    source_url: str | None = None,
) -> ChunkContext:
    """Build one authorized context row.

    Args:
        candidate: Fused candidate identity.
        text: Canonical citation text.
        page: Optional page locator.
        section: Heading path.
        sheet_name: Optional sheet locator.
        range_ref: Optional range locator.
        source_url: Optional URL locator.

    Returns:
        Frozen chunk context.
    """

    return ChunkContext(
        chunk_id=candidate.chunk_id,
        document_id=candidate.document_id,
        version_id=candidate.version_id,
        parent_chunk_id=None,
        chunk_index=0,
        page_number=page,
        section_path=section,
        token_count=max(1, len(text.split())),
        raw_text=text,
        is_search_representative=True,
        sheet_name=sheet_name,
        range_ref=range_ref,
        source_url=source_url,
    )


def _retriever(
    *,
    contexts: dict[UUID, ChunkContext] | None = None,
    adapter: MockEmbeddingAdapter | None = None,
    rerank_calls: list[int] | None = None,
) -> HybridRetriever:
    """Build a HybridRetriever with a mock embedding gateway.

    Args:
        contexts: Optional authorized rows keyed by chunk id.
        adapter: Optional embedding adapter (for call accounting).
        rerank_calls: Optional list that records rerank model_calls.

    Returns:
        Retriever that uses injected loaders rather than live databases.
    """

    rows = contexts or {}

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return cached authorized rows.

        Args:
            ids: Requested IDs.

        Returns:
            Matching context rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    def rerank(
        _query: str,
        pool: tuple[RerankPassage, ...],
        _deadline: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Return fused order with no model usage unless recorded.

        Args:
            _query: Unused.
            pool: Authorized pool.
            _deadline: Unused.

        Returns:
            Identity rankings.
        """

        usage = None
        if rerank_calls is not None:
            rerank_calls.append(1)
            usage = RerankUsage(
                request_id="test",
                model="gpt-4o-mini",
                input_tokens=1,
                output_tokens=1,
                model_calls=1,
            )
        rankings = tuple(
            RerankRanking(chunk_id=item.candidate.chunk_id, rank=index + 1, support=1.0)
            for index, item in enumerate(pool)
        )
        return rankings, usage, RerankFallbackReason.NONE

    return HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            adapter or MockEmbeddingAdapter(fixture_id="hybrid-run")
        ),
        load_context=load,
        rerank=rerank,
    )


def test_flatten_channel_candidates_dedupes_first_seen() -> None:
    """Temporal lookup sees each chunk once across dense, BM25, and term."""

    from smart_rag_core.retrieval.hybrid_run import _flatten_channel_candidates

    first = _candidate(rank=1)
    second = _candidate(rank=2)
    bm25_dup = RetrievalCandidate(
        chunk_id=first.chunk_id,
        document_id=first.document_id,
        version_id=first.version_id,
        channel_rank=3,
        channel_score=0.1,
    )
    flat = _flatten_channel_candidates(((first,),), (bm25_dup, second), ())
    assert tuple(item.chunk_id for item in flat) == (first.chunk_id, second.chunk_id)


def test_retrieval_slice_is_statement_timeout_bound() -> None:
    """The retrieve+rerank slice is the 8s statement-timeout bound, not 25s."""

    assert RETRIEVAL_SLICE_SECONDS == 8.0
    assert RetrievalFallbackReason.DENSE_UNAVAILABLE == "dense_unavailable"
    assert RetrievalFallbackReason.TERM_UNAVAILABLE == "term_unavailable"
    assert RetrievalFallbackReason.AUTH_CONTEXT_INVALID == "auth_context_invalid"
    assert RetrievalFallbackReason.RETRIEVAL_EMPTY == "retrieval_empty"
    assert RetrievalFallbackReason.TIMEOUT == "retrieval_timeout"


def test_assemble_hybrid_deadline_exhausted_param() -> None:
    """Optional deadline_exhausted is recorded without rewriting fusion."""

    item = _candidate()
    result = assemble_hybrid(
        dense_variants=((item,),),
        bm25_variants=(),
        term_variants=(),
        principal_scope_hash="abc",
        query_normalized="query",
        visibility_generation=1,
        deadline_exhausted=True,
    )
    assert result.deadline_exhausted is True
    assert result.fused[0].chunk_id == item.chunk_id


def test_dense_cap_holds_for_hybrid_retriever() -> None:
    """Dense channel overflow is capped at 100 authorized IDs."""

    overflow = tuple(_candidate(rank=index) for index in range(1, 121))
    contexts = {
        item.chunk_id: _context(item, text=f"canonical {index}")
        for index, item in enumerate(overflow)
    }
    retriever = _retriever(contexts=contexts)
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={"dense": lambda: overflow},
    )
    assert len(result.ranked_ids) <= DENSE_CANDIDATE_CAP
    assert result.embedding_call_count == 1
    assert result.first_evidence_ms >= 0.0


def test_bm25_and_term_caps_hold() -> None:
    """BM25 survivors cap at 75 and term candidates cap at 30."""

    bm25 = tuple(_candidate(rank=index) for index in range(1, 81))
    term = tuple(_candidate(rank=index) for index in range(1, 41))
    contexts = {
        item.chunk_id: _context(item, text="canonical") for item in (*bm25, *term)
    }
    retriever = _retriever(contexts=contexts)
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={
            "bm25": lambda: Bm25RetrievalResult(scanned_ids=(), candidates=bm25),
            "term": lambda: term,
        },
    )
    assert len(result.ranked_ids) <= BM25_AUTHORIZED_SURVIVOR_CAP + TERM_CANDIDATE_CAP
    bm25_ids = {item.chunk_id for item in bm25}
    term_ids = {item.chunk_id for item in term}
    assert len(bm25_ids.intersection(result.ranked_ids)) <= BM25_AUTHORIZED_SURVIVOR_CAP
    assert len(term_ids.intersection(result.ranked_ids)) <= TERM_CANDIDATE_CAP


def test_bm25_degradation_continues_dense_and_term() -> None:
    """ParadeDB outage records bm25_unavailable and keeps dense+term IDs."""

    dense = _candidate(rank=1)
    term = _candidate(rank=1)
    contexts = {
        dense.chunk_id: _context(dense, text="canonical dense"),
        term.chunk_id: _context(term, text="canonical term"),
    }
    retriever = _retriever(contexts=contexts)
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={
            "dense": lambda: (dense,),
            "bm25": lambda: Bm25RetrievalResult(
                scanned_ids=(),
                candidates=(),
                fallback_reason=RetrievalFallbackReason.BM25_UNAVAILABLE,
            ),
            "term": lambda: (term,),
        },
    )
    assert result.fallback_reason is RetrievalFallbackReason.BM25_UNAVAILABLE
    assert dense.chunk_id in result.ranked_ids
    assert term.chunk_id in result.ranked_ids
    assert result.deadline_exhausted is False


def test_empty_query_fail_closed_skips_channels() -> None:
    """Blank queries fail closed with retrieval_empty and do not retrieve."""

    ran = {"value": False}

    def boom() -> object:
        """Mark that a channel ran.

        Returns:
            Never returns because the test must not call this job.
        """

        ran["value"] = True
        raise AssertionError("must not retrieve")

    retriever = _retriever()
    result = retriever.retrieve(
        query="   ",
        caller=_caller(),
        channel_jobs={"dense": boom},
    )
    assert result.fallback_reason is RetrievalFallbackReason.RETRIEVAL_EMPTY
    assert result.ranked_ids == ()
    assert result.evidence == ()
    assert result.embedding_call_count == 0
    assert ran["value"] is False


def test_over_max_query_chars_fail_closed() -> None:
    """Queries over 512 normalized characters fail closed, not unbounded retrieve."""

    ran = {"value": False}

    def boom() -> object:
        """Mark that a channel ran.

        Returns:
            Never.
        """

        ran["value"] = True
        return ()

    retriever = _retriever()
    result = retriever.retrieve(
        query="x" * (MAX_NORMALIZED_QUERY_CHARS + 1),
        caller=_caller(),
        channel_jobs={"dense": boom},
    )
    assert result.fallback_reason is RetrievalFallbackReason.RETRIEVAL_EMPTY
    assert result.embedding_call_count == 0
    assert ran["value"] is False


def test_disabled_caller_is_auth_context_invalid() -> None:
    """Disabled callers fail closed before channel work."""

    retriever = _retriever()
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(disabled=True),
        channel_jobs={"dense": lambda: (_candidate(),)},
    )
    assert result.fallback_reason is RetrievalFallbackReason.AUTH_CONTEXT_INVALID
    assert result.embedding_call_count == 0


def test_channel_timeout_sets_deadline_exhausted() -> None:
    """A timed-out channel sets deadline_exhausted and a named fallback."""

    dense = _candidate(rank=1)
    contexts = {dense.chunk_id: _context(dense, text="canonical dense")}
    retriever = _retriever(contexts=contexts)

    def hang() -> object:
        """Exceed the test slice.

        Returns:
            Unused BM25 result after sleep.
        """

        time.sleep(0.25)
        return Bm25RetrievalResult(scanned_ids=(), candidates=())

    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        deadline_seconds=0.05,
        channel_jobs={
            "dense": lambda: (dense,),
            "bm25": hang,
        },
    )
    assert result.deadline_exhausted is True
    assert result.fallback_reason is RetrievalFallbackReason.TIMEOUT
    assert dense.chunk_id in result.ranked_ids


def test_dense_timeout_named_fallback() -> None:
    """Dense channel timeout records dense_unavailable."""

    retriever = _retriever()

    def hang() -> object:
        """Exceed the test slice.

        Returns:
            Unused dense list.
        """

        time.sleep(0.25)
        return ()

    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        deadline_seconds=0.05,
        channel_jobs={"dense": hang, "term": lambda: ()},
    )
    assert result.deadline_exhausted is True
    assert result.fallback_reason is RetrievalFallbackReason.DENSE_UNAVAILABLE


def test_evidence_capped_at_twelve() -> None:
    """Final evidence never exceeds 12 units."""

    fused = tuple(_candidate(rank=index) for index in range(1, 21))
    contexts = {
        item.chunk_id: _context(item, text=f"canonical passage {index}")
        for index, item in enumerate(fused)
    }
    retriever = _retriever(contexts=contexts)
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={"dense": lambda: fused},
    )
    assert len(result.evidence) <= FINAL_EVIDENCE_MAX
    assert FINAL_EVIDENCE_MAX == 12


def test_citation_text_comes_from_chunk_context_not_bm25() -> None:
    """Citation text is ChunkContext.raw_text; BM25 snippets are never evidence."""

    item = _candidate(rank=1)
    canonical = "canonical leave policy from supabase"
    contexts = {
        item.chunk_id: _context(
            item,
            text=canonical,
            page=4,
            section=("Benefits", "Leave"),
            sheet_name="Hours",
            range_ref="B2:D10",
            source_url="https://example.invalid/leave",
        )
    }
    retriever = _retriever(contexts=contexts)
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={
            "bm25": lambda: Bm25RetrievalResult(
                scanned_ids=(item.chunk_id,),
                candidates=(item,),
            )
        },
    )
    assert result.evidence
    unit = result.evidence[0]
    assert unit.citation_text == canonical
    assert BM25_SNIPPET not in unit.citation_text
    assert unit.locator.page_number == 4
    assert unit.locator.section_path == ("Benefits", "Leave")
    assert unit.locator.sheet_name == "Hours"
    assert unit.locator.range_ref == "B2:D10"
    assert unit.locator.source_url == "https://example.invalid/leave"


def test_one_batched_embedding_call_for_original_and_variants() -> None:
    """Original plus at most three variants is one gateway invocation."""

    class _RecordingAdapter(MockEmbeddingAdapter):
        """Count embed batches for query-time accounting."""

        def __init__(self) -> None:
            """Initialize call accounting."""

            super().__init__(fixture_id="hybrid-run")
            self.batches: list[tuple[str, ...]] = []

        async def embed(self, request: EmbeddingRequest):
            """Record one batch then delegate to the mock vectors.

            Args:
                request: Bounded embedding batch.

            Returns:
                Mock embedding response.
            """

            self.batches.append(request.inputs)
            return await super().embed(request)

    adapter = _RecordingAdapter()
    item = _candidate()
    contexts = {item.chunk_id: _context(item, text="canonical")}
    retriever = _retriever(contexts=contexts, adapter=adapter)
    profile = profile_query_sync("annual leave policy").profile.model_copy(
        update={
            "variants": det(["leave policy days", "annual vacation rules"]),
        }
    )
    result = retriever.retrieve(
        query="annual leave policy",
        caller=_caller(),
        profile=profile,
        channel_jobs={"dense": lambda: (item,)},
    )
    assert result.embedding_call_count == 1
    assert len(adapter.batches) == 1
    assert adapter.batches[0][0] == "annual leave policy"
    assert len(adapter.batches[0]) == 3


def test_mocked_retrievers_compose_ranked_ids() -> None:
    """HybridRetriever.retrieve calls mocked channel retrievers."""

    dense = _candidate(rank=1)
    contexts = {dense.chunk_id: _context(dense, text="canonical dense")}

    class _Dense:
        """Fake dense retriever."""

        def retrieve(self, **_kwargs: object) -> DenseRetrievalResult:
            """Return one authorized dense hit.

            Returns:
                Dense result.
            """

            return DenseRetrievalResult(
                mode=DenseMode.ANN,
                candidates=(dense,),
                authorized_count=1,
            )

    class _Bm25:
        """Fake BM25 retriever that stays available but empty."""

        def retrieve(self, **_kwargs: object) -> Bm25RetrievalResult:
            """Return an empty authorized BM25 list.

            Returns:
                Empty BM25 result.
            """

            return Bm25RetrievalResult(scanned_ids=(), candidates=())

    class _Term:
        """Fake term retriever."""

        def retrieve(self, **_kwargs: object) -> TermRetrievalResult:
            """Return an empty term channel.

            Returns:
                Empty term result.
            """

            return TermRetrievalResult(
                candidates=(),
                query_normalized="annual leave policy",
                empty_channel=True,
            )

    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="hybrid-run")
        ),
        dense=_Dense(),
        bm25=_Bm25(),
        term=_Term(),
        load_context=lambda ids: tuple(
            contexts[item] for item in ids if item in contexts
        ),
    )
    result = retriever.retrieve(query="annual leave policy", caller=_caller())
    assert dense.chunk_id in result.ranked_ids
    assert result.embedding_call_count == 1


def test_channel_supabase_opens_dedicated_connection_from_full_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live channels clone from the full DSN, not password-less ``info.dsn``."""

    opened: list[str] = []
    closed: list[int] = []

    class _Conn:
        """Stand-in connection that records close()."""

        def close(self) -> None:
            """Record that the channel connection was closed."""

            closed.append(1)

    def _connect(dsn: str, **_kwargs: object) -> _Conn:
        """Record the DSN used to open a channel connection.

        Args:
            dsn: Caller-supplied Postgres URL.
            **_kwargs: Ignored connect kwargs.

        Returns:
            Dummy connection.
        """

        opened.append(dsn)
        return _Conn()

    monkeypatch.setattr(
        "smart_rag_core.retrieval.hybrid_run.psycopg.connect",
        _connect,
    )
    dsn = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    retriever = HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="hybrid-run")
        ),
        supabase_dsn=dsn,
    )
    with retriever._channel_supabase() as conn:
        assert isinstance(conn, _Conn)
    assert opened == [dsn]
    assert closed == [1]


def test_locators_from_provenance_round_trip_sheet_and_url() -> None:
    """Sheet, range, and URL are parsed from locator_to_dict provenance."""

    sheet, range_ref, url = locators_from_provenance(
        {
            "locators": [
                {
                    "format": "xlsx",
                    "sheet_name": "Q1",
                    "range_ref": "A1:C4",
                    "cell_ref": "A1",
                },
                {
                    "format": "html",
                    "source_url": "https://example.invalid/policy",
                },
            ]
        }
    )
    assert sheet == "Q1"
    assert range_ref == "A1:C4"
    assert url == "https://example.invalid/policy"
    inventory = heading_inventory_from_contexts(
        (
            _context(_candidate(), text="a", section=("Payroll", "Overtime")),
            _context(_candidate(), text="b", section=("Payroll", "Overtime")),
            _context(_candidate(), text="c", section=("Benefits",)),
        )
    )
    assert inventory == ("Payroll/Overtime", "Benefits")
