"""Hybrid stage timings, rerank validation sub-codes, and export flags (A2)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from smart_rag_core.gateways.embedding import EmbeddingGateway, MockEmbeddingAdapter
from smart_rag_core.gateways.model import RerankModelRequest, RerankModelResponse
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branch_channels.hybrid import (
    hybrid_diagnostics_from_outcome,
)
from smart_rag_core.query_routing.models import HybridBranchDiagnostics
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.hybrid import run_channels_parallel
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_core.retrieval.profiles import (
    HYBRID_DEFAULT_PROFILE_ID,
    HYBRID_STAGE_TIMING_KEYS,
    RERANK_INVALID_SUBCODES,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankPayloadError,
    RerankRanking,
    RerankUsage,
    rerank_input_hash,
    validate_rerank_payload,
)
from smart_rag_core.retrieval.reranker import rerank_pool
from smart_rag_core.retrieval.types import Bm25RetrievalResult, RetrievalCandidate
from smart_rag_core.security.identity import CallerContext, UserRole

from scripts.eval_ask_stage_export import (
    bm25_explicit_flag,
    bm25_record_keeps_aggregate,
    stage_record,
)

_RerankTriple = tuple[
    tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason
]
_ALWAYS = frozenset(
    {
        "embed_ms",
        "channels_ms",
        "assemble_ms",
        "temporal_load_ms",
        "pool_preload_ms",
        "rerank_gate_remaining_ms",
        "selection_ms",
        "locator_reload_ms",
        "retrieve_total_ms",
    }
)


def _caller() -> CallerContext:
    """Build an active member caller.

    Returns:
        Server-derived caller context.
    """

    return CallerContext(
        user_id=str(uuid4()), role=UserRole.MEMBER, authorization_version=1
    )


def _candidate(rank: int = 1) -> RetrievalCandidate:
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


def _retriever(
    rows: dict[UUID, ChunkContext], triple: _RerankTriple | None = None
) -> HybridRetriever:
    """Build a retriever with mock embeddings and an injected rerank.

    Args:
        rows: Authorized context rows by chunk id.
        triple: Fixed rerank result. ``None`` returns identity rankings.

    Returns:
        Retriever that uses no database.
    """

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return authorized rows for the requested IDs.

        Args:
            ids: Requested chunk IDs.

        Returns:
            Matching rows.
        """

        return tuple(rows[item] for item in ids if item in rows)

    def rerank(
        _query: str, pool: tuple[RerankPassage, ...], _deadline: float
    ) -> _RerankTriple:
        """Return the fixed triple, or identity rankings with one call.

        Args:
            _query: Unused.
            pool: Authorized pool.
            _deadline: Unused.

        Returns:
            Rerank triple.
        """

        if triple is not None:
            return triple
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

    return HybridRetriever(
        embedding_gateway=EmbeddingGateway(
            MockEmbeddingAdapter(fixture_id="hybrid-run")
        ),
        load_context=load,
        rerank=rerank,
    )


def _is_ms(value: object) -> bool:
    """Return whether a timing value is a non-negative int (not bool).

    Args:
        value: Timing value.

    Returns:
        True for a non-negative integer.
    """

    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def test_retrieve_records_non_negative_stage_timings() -> None:
    """Every measured stage is a known key with non-negative integer ms."""

    dense, bm25, term = _candidate(), _candidate(), _candidate()
    rows = {
        dense.chunk_id: _context(dense, "annual leave accrues monthly"),
        bm25.chunk_id: _context(bm25, "leave carry over rules"),
        term.chunk_id: _context(term, "leave policy definitions"),
    }
    result = _retriever(rows).retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={
            "dense": lambda: (dense,),
            "bm25": lambda: Bm25RetrievalResult(scanned_ids=(), candidates=(bm25,)),
            "term": lambda: (term,),
        },
    )
    timings = result.stage_timings_ms
    assert set(timings) >= _ALWAYS
    assert {"channel_dense_ms", "channel_bm25_ms", "channel_term_ms"} <= set(timings)
    assert "rerank_call_ms" in timings
    assert "scope_ms" not in timings
    assert set(timings) <= HYBRID_STAGE_TIMING_KEYS
    assert all(_is_ms(value) for value in timings.values())
    assert result.rerank_invalid_subcode == ""


def test_timed_out_channel_and_gate_skip_have_no_duration() -> None:
    """A timed-out channel has no key; a gate skip records no rerank call."""

    first, second = _candidate(1), _candidate(2)
    rows = {
        first.chunk_id: _context(first, "annual leave accrues monthly"),
        second.chunk_id: _context(second, "leave carry over rules"),
    }

    def hang() -> object:
        """Outlive the tiny test slice.

        Returns:
            An empty BM25 result after the slice has expired.
        """

        time.sleep(0.25)
        return Bm25RetrievalResult(scanned_ids=(), candidates=())

    result = _retriever(rows).retrieve(
        query="annual leave policy",
        caller=_caller(),
        deadline_seconds=0.05,
        channel_jobs={"dense": lambda: (first, second), "bm25": hang},
    )
    timings = result.stage_timings_ms
    assert result.deadline_exhausted is True
    assert "channel_dense_ms" in timings
    assert "channel_bm25_ms" not in timings
    assert "rerank_call_ms" not in timings
    assert timings["rerank_gate_remaining_ms"] <= 50
    assert result.rerank_fallback == RerankFallbackReason.TIMEOUT.value


def test_schema_invalid_subcode_reaches_the_result() -> None:
    """The sub-code rides on rerank usage into the retrieve result."""

    first, second = _candidate(1), _candidate(2)
    rows = {
        first.chunk_id: _context(first, "annual leave accrues monthly"),
        second.chunk_id: _context(second, "leave carry over rules"),
    }
    usage = RerankUsage(
        request_id="r",
        model="gpt-4o-mini",
        input_tokens=3,
        output_tokens=2,
        model_calls=1,
        invalid_subcode="hash",
    )
    triple: _RerankTriple = ((), usage, RerankFallbackReason.SCHEMA_INVALID)
    result = _retriever(rows, triple).retrieve(
        query="annual leave policy",
        caller=_caller(),
        channel_jobs={"dense": lambda: (first, second)},
    )
    assert result.rerank_fallback == RerankFallbackReason.SCHEMA_INVALID.value
    assert result.rerank_invalid_subcode == "hash"
    assert "rerank_call_ms" in result.stage_timings_ms


def test_rerank_pool_records_json_subcode_without_retry() -> None:
    """A parsed payload with the wrong shape is schema-invalid with ``json``."""

    calls: list[str] = []

    class _Gateway:
        """Return one payload that lacks the ranking fields."""

        async def generate_rerank(
            self, request: RerankModelRequest
        ) -> RerankModelResponse:
            """Record the call and return a shape-invalid payload.

            Args:
                request: Structured rerank request.

            Returns:
                Response whose payload has only ``status``.
            """

            calls.append(request.prompt_version)
            return RerankModelResponse(
                mode="mock",
                payload={"status": "complete"},
                request_id="fake-rerank",
                input_tokens=5,
                output_tokens=2,
            )

    pool = (
        RerankPassage(candidate=_candidate(1), raw_text="alpha", excerpt="alpha"),
        RerankPassage(candidate=_candidate(2), raw_text="beta", excerpt="beta"),
    )
    rankings, usage, reason = rerank_pool(
        "q",
        pool,
        8.0,
        gateway=_Gateway(),  # type: ignore[arg-type]
        prompt_text="rank",
    )
    assert len(calls) == 1
    assert rankings == ()
    assert reason is RerankFallbackReason.SCHEMA_INVALID
    assert usage is not None
    assert usage.invalid_subcode == "json"
    assert usage.output_tokens == 2


def test_v1_validation_errors_carry_one_subcode_each() -> None:
    """Each rerank_v1 check raises RerankPayloadError with its sub-code."""

    first, second = uuid4(), uuid4()
    digest = rerank_input_hash(
        query="q",
        candidate_ids=(str(first), str(second)),
        excerpts=("a", "b"),
        prompt_sha256="0" * 64,
    )
    good: list[dict[str, object]] = [
        {"chunk_id": str(first), "rank": 1, "support": 0.9},
        {"chunk_id": str(second), "rank": 2, "support": 0.1},
    ]
    extra: dict[str, object] = {"chunk_id": str(uuid4()), "rank": 3, "support": 0.0}
    cases: list[tuple[object, str, str]] = [
        ({"status": "complete"}, "rerank_schema_invalid", "json"),
        (
            {"status": "complete", "input_hash": "f" * 64, "rankings": good},
            "rerank_input_hash_mismatch",
            "hash",
        ),
        (
            {"status": "complete", "input_hash": digest, "rankings": [*good, extra]},
            "rerank_ranking_length",
            "length",
        ),
        (
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [good[0], {**good[0], "rank": 2}],
            },
            "rerank_duplicate_id",
            "duplicate",
        ),
        (
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [good[0], {**good[1], "rank": 1}],
            },
            "rerank_rank_invalid",
            "duplicate",
        ),
        (
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [{**good[0], "chunk_id": str(uuid4())}, good[1]],
            },
            "rerank_unknown_or_missing_id",
            "unknown_id",
        ),
    ]
    for payload, message, subcode in cases:
        with pytest.raises(RerankPayloadError) as caught:
            validate_rerank_payload(
                payload, candidate_ids=(first, second), input_hash=digest
            )
        assert str(caught.value) == message
        assert caught.value.subcode == subcode
    assert issubclass(RerankPayloadError, ValueError)
    assert frozenset({"json", "hash", "length", "duplicate", "unknown_id"}) == (
        RERANK_INVALID_SUBCODES
    )
    with pytest.raises(ValueError, match="rerank_subcode_invalid"):
        RerankPayloadError("x", subcode="other")


def test_diagnostics_keep_known_timings_and_reject_bad_ones() -> None:
    """The builder drops bad values; the model rejects them outright."""

    chunk = str(uuid4())
    outcome = SimpleNamespace(
        source_resolution="unscoped",
        retrieval_profile_id=HYBRID_DEFAULT_PROFILE_ID,
        rerank_fallback="rerank_schema_invalid",
        rerank_call_count=1,
        embedding_call_count=1,
        first_evidence_ms=4.0,
        dense_ids=(chunk,),
        fused_ids=(chunk,),
        selected_ids=(chunk,),
        stage_timings_ms={
            "embed_ms": 120,
            "channels_ms": 2400,
            "not_a_stage_ms": 5,
            "selection_ms": -1,
            "rerank_call_ms": True,
        },
        rerank_invalid_subcode="length",
    )
    row = hybrid_diagnostics_from_outcome(
        outcome, effective_route=Phase6RouteFamily.HYBRID.value, fallback_reason="none"
    )
    assert row is not None
    assert row.stage_timings_ms == {"embed_ms": 120, "channels_ms": 2400}
    assert row.rerank_invalid_subcode == "length"
    bare = hybrid_diagnostics_from_outcome(
        SimpleNamespace(
            source_resolution="unscoped",
            retrieval_profile_id=HYBRID_DEFAULT_PROFILE_ID,
            rerank_invalid_subcode="free text",
        ),
        effective_route=Phase6RouteFamily.HYBRID.value,
        fallback_reason="none",
    )
    assert bare is not None
    assert bare.rerank_invalid_subcode == ""
    assert bare.stage_timings_ms == {}
    base = row.model_dump()
    for bad in (
        {"stage_timings_ms": {"query_text": 1}},
        {"stage_timings_ms": {"embed_ms": -3}},
        {"rerank_invalid_subcode": "other"},
    ):
        with pytest.raises(ValidationError):
            HybridBranchDiagnostics.model_validate({**base, **bad})


def test_stage_record_exports_new_fields_and_fixed_bm25_flag() -> None:
    """Export copies the fields; ``none`` and empty are not explicit BM25."""

    chunk = str(uuid4())
    diagnostics: dict[str, object] = {
        "source_resolution": "unscoped",
        "retrieval_profile_id": HYBRID_DEFAULT_PROFILE_ID,
        "fallback_reason": "none",
        "rerank_fallback": "rerank_schema_invalid",
        "rerank_call_count": 1,
        "embedding_call_count": 1,
        "dense_ids": [chunk],
        "bm25_ids": [chunk],
        "term_ids": [chunk],
        "fused_ids": [chunk],
        "selected_ids": [chunk],
        "rerank_pool_ids": [chunk],
        "effective_route": "hybrid",
        "stage_timings_ms": {"embed_ms": 110, "rerank_call_ms": 4200},
        "rerank_invalid_subcode": "duplicate",
    }
    record = stage_record(diagnostics, {"embedding", "rerank"})
    assert record["stage_timings_ms"] == {"embed_ms": 110, "rerank_call_ms": 4200}
    assert record["rerank_invalid_subcode"] == "duplicate"
    assert record["bm25_degraded_explicit"] is False
    legacy = stage_record(
        {
            key: value
            for key, value in diagnostics.items()
            if key not in {"stage_timings_ms", "rerank_invalid_subcode"}
        },
        {"embedding", "rerank"},
    )
    assert legacy["stage_timings_ms"] == "unknown"
    assert legacy["rerank_invalid_subcode"] == "unknown"
    empty = stage_record({**diagnostics, "fallback_reason": ""}, {"embedding"})
    assert empty["fallback_reason"] == "unknown"
    assert empty["bm25_degraded_explicit"] is False
    assert bm25_explicit_flag("none") is False
    assert bm25_explicit_flag("") is False
    assert bm25_explicit_flag("term_unavailable") is False
    assert bm25_explicit_flag("bm25_unavailable") is True
    assert bm25_explicit_flag("timeout") is True
    assert bm25_explicit_flag("unknown") == "unknown"
    assert bm25_record_keeps_aggregate(record) is True
    masked = {"fallback_reason": "term_unavailable", "bm25_degraded_explicit": False}
    named = {"fallback_reason": "bm25_unavailable", "bm25_degraded_explicit": True}
    unknown = {"fallback_reason": "unknown", "bm25_degraded_explicit": "unknown"}
    assert bm25_record_keeps_aggregate(masked) is False
    assert bm25_record_keeps_aggregate(named) is True
    assert bm25_record_keeps_aggregate(unknown) is False


def test_run_channels_parallel_measures_only_finished_channels() -> None:
    """Finished channels get a duration; timed-out channels get none."""

    def slow() -> object:
        """Outlive the deadline.

        Returns:
            An empty tuple after the deadline.
        """

        time.sleep(0.25)
        return ()

    durations: dict[str, int] = {}
    completed, timed_out, exhausted = run_channels_parallel(
        {"dense": lambda: ("d",), "bm25": slow},
        deadline_seconds=0.05,
        durations_ms=durations,
    )
    assert completed == {"dense": ("d",)}
    assert timed_out == ("bm25",)
    assert exhausted is True
    assert set(durations) == {"dense"}
    assert durations["dense"] >= 0
