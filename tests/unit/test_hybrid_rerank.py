"""Unit tests for Phase 4 Packet 5 rerank, MMR, quotas, and parent expansion."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from smart_rag_agents.prompts import rerank_prompt_text
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.evaluation.loader import load_open_splits
from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.gateways.model import create_model_gateway
from smart_rag_core.gateways.openai_rerank import OpenAIRerankError
from smart_rag_core.retrieval.context import (
    expand_parents,
    passages_from_context,
    select_hybrid_context,
)
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.profiles import (
    RERANK_MAX_PER_DOCUMENT,
    RERANK_POOL_SIZE,
)
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
    apply_mmr,
    build_rerank_pool,
    rerank_input_hash,
    rerank_json_schema,
    rerank_preload_ids,
    should_skip_trivial_exact,
    trim_token_budget,
    validate_rerank_payload,
)
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)
from smart_rag_core.retrieval.reranker import rerank_pool
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.settings import AgentSettings

from tests.unit.typed_openapi import json_object


def _candidate(
    chunk: UUID | None = None, document: UUID | None = None
) -> RetrievalCandidate:
    """Build one fused candidate.

    Args:
        chunk: Optional chunk id.
        document: Optional document id.

    Returns:
        Frozen candidate.
    """

    return RetrievalCandidate(
        chunk_id=chunk or uuid4(),
        document_id=document or uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def _passage(
    *,
    document: UUID | None = None,
    text: str = "policy text",
    channels: frozenset[str] = frozenset({"dense"}),
    parent: UUID | None = None,
    section: tuple[str, ...] = (),
) -> RerankPassage:
    """Build one rerank passage.

    Args:
        document: Shared document id for quota tests.
        text: Canonical text.
        channels: Channel membership.
        parent: Optional parent id.
        section: Heading path.

    Returns:
        Passage wrapping a new candidate.
    """

    candidate = _candidate(document=document)
    return RerankPassage(
        candidate=candidate,
        raw_text=text,
        section_path=section,
        parent_chunk_id=parent,
        token_count=max(1, len(text.split())),
        channels=channels,
        excerpt=text,
    )


def _identity_rerank(
    _query: str,
    pool: tuple[RerankPassage, ...],
    deadline: float,
) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
    """Preserve fused order as a successful rerank.

    Args:
        _query: Unused query.
        pool: Rerank pool.
        deadline: Remaining seconds.

    Returns:
        Identity rankings or a budget denial.
    """

    if deadline <= 0:
        return (), None, RerankFallbackReason.BUDGET_DENIED
    rankings = tuple(
        RerankRanking(chunk_id=item.candidate.chunk_id, rank=index, support=0.5)
        for index, item in enumerate(pool, start=1)
    )
    usage = RerankUsage(
        request_id="test",
        model="mock",
        input_tokens=0,
        output_tokens=0,
        model_calls=1,
    )
    return rankings, usage, RerankFallbackReason.NONE


def test_pool_caps_and_per_document_quota() -> None:
    """The pool keeps 20 IDs and at most five passages per document."""

    document = uuid4()
    overflow = tuple(
        _passage(document=document, text=f"dup {index}") for index in range(8)
    )
    others = tuple(_passage(text=f"other {index}") for index in range(20))
    pool = build_rerank_pool(overflow + others)
    assert len(pool) <= RERANK_POOL_SIZE
    assert sum(1 for item in pool if item.candidate.document_id == document) <= (
        RERANK_MAX_PER_DOCUMENT
    )


def test_rerank_preload_ids_match_pool_membership() -> None:
    """Preload IDs follow the same per-document pool cap as the reranker."""

    document = uuid4()
    overflow = tuple(_candidate(document=document) for _ in range(8))
    others = tuple(_candidate() for _ in range(20))
    fused = overflow + others
    preloaded = rerank_preload_ids(
        fused,
        pool_size=RERANK_POOL_SIZE,
        max_per_document=RERANK_MAX_PER_DOCUMENT,
    )
    assert len(preloaded) == RERANK_POOL_SIZE
    assert len(preloaded) == len(set(preloaded))
    from_overflow = [
        item for item in preloaded if item in {row.chunk_id for row in overflow}
    ]
    assert len(from_overflow) <= RERANK_MAX_PER_DOCUMENT


def test_skip_only_trivial_exact_with_two_channels() -> None:
    """Score gaps never skip; exact code with two channels does."""

    cases = [
        case for case in load_open_splits() if case.query_class is QueryClass.EXACT_CODE
    ]
    profile = cases[0].expected_profile
    assert str(profile.query_type.value) == QueryType.EXACT_IDENTIFIER.value
    winner = _passage(channels=frozenset({"bm25", "term"}), text="INV-SR status")
    second = _passage(channels=frozenset({"dense"}), text="other")
    assert should_skip_trivial_exact(profile, (winner, second)) is True
    semantic = next(
        case.expected_profile
        for case in load_open_splits()
        if case.query_class is QueryClass.SEMANTIC_FACTUAL
    )
    assert should_skip_trivial_exact(semantic, (winner, second)) is False
    single = _passage(channels=frozenset({"term"}), text="INV-SR status")
    assert should_skip_trivial_exact(profile, (single, second)) is False


def test_schema_rejects_unknown_duplicate_missing_and_support() -> None:
    """Application set-equality rejects malformed rerank payloads."""

    first = uuid4()
    second = uuid4()
    ids = (str(first), str(second))
    digest = rerank_input_hash(
        query="q",
        candidate_ids=ids,
        excerpts=("a", "b"),
        prompt_sha256="0" * 64,
    )
    schema = rerank_json_schema(ids, input_hash=digest)
    properties = json_object(schema["properties"])
    rankings_schema = json_object(properties["rankings"])
    assert rankings_schema["maxItems"] == 2
    ranking_rows: list[dict[str, str | int | float]] = [
        {"chunk_id": str(first), "rank": 1, "support": 0.9},
        {"chunk_id": str(second), "rank": 2, "support": 0.1},
    ]
    valid: dict[str, object] = {
        "status": "complete",
        "input_hash": digest,
        "rankings": ranking_rows,
    }
    parsed = validate_rerank_payload(
        valid, candidate_ids=(first, second), input_hash=digest
    )
    assert [item.chunk_id for item in parsed] == [first, second]
    with pytest.raises(ValueError, match="rerank_duplicate_id"):
        validate_rerank_payload(
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [
                    {"chunk_id": str(first), "rank": 1, "support": 0.9},
                    {"chunk_id": str(first), "rank": 2, "support": 0.1},
                ],
            },
            candidate_ids=(first, second),
            input_hash=digest,
        )
    with pytest.raises(ValueError, match="rerank_unknown_or_missing_id"):
        validate_rerank_payload(
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [
                    {"chunk_id": str(uuid4()), "rank": 1, "support": 0.9},
                    {"chunk_id": str(second), "rank": 2, "support": 0.1},
                ],
            },
            candidate_ids=(first, second),
            input_hash=digest,
        )
    with pytest.raises(ValueError, match="rerank_support_out_of_bounds"):
        validate_rerank_payload(
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [
                    {"chunk_id": str(first), "rank": 1, "support": 1.5},
                    {"chunk_id": str(second), "rank": 2, "support": 0.1},
                ],
            },
            candidate_ids=(first, second),
            input_hash=digest,
        )
    with pytest.raises(ValueError, match="rerank_input_hash_mismatch"):
        validate_rerank_payload(
            {**valid, "input_hash": "f" * 64},
            candidate_ids=(first, second),
            input_hash=digest,
        )
    with pytest.raises(ValueError, match="rerank_ranking_length"):
        validate_rerank_payload(
            {
                "status": "complete",
                "input_hash": digest,
                "rankings": [
                    *ranking_rows,
                    {"chunk_id": str(uuid4()), "rank": 3, "support": 0.0},
                ],
            },
            candidate_ids=(first, second),
            input_hash=digest,
        )
    with pytest.raises(ValueError, match="rerank_incomplete"):
        validate_rerank_payload(
            {**valid, "status": "incomplete"},
            candidate_ids=(first, second),
            input_hash=digest,
        )


def test_prompt_hash_matches_checked_in_file() -> None:
    """The frozen rerank prompt hash matches the agents prompt file."""

    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "agents"
        / "src"
        / "smart_rag_agents"
        / "prompts"
        / "rerank_v1.md"
    )
    digest = hashlib.sha256(
        prompt_path.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    assert digest == RERANK_PROMPT_SHA256
    assert RERANK_PROMPT_VERSION in prompt_path.read_text(encoding="utf-8")


def test_rerank_failure_falls_back_to_rrf_order() -> None:
    """Invalid/timeout rerank keeps deterministic fused order."""

    first = _passage(text="alpha unique tokens here")
    second = _passage(text="beta completely different words")
    fused = (first.candidate, second.candidate)
    contexts = (
        ChunkContext(
            chunk_id=first.candidate.chunk_id,
            document_id=first.candidate.document_id,
            version_id=first.candidate.version_id,
            parent_chunk_id=None,
            chunk_index=0,
            page_number=1,
            section_path=(),
            token_count=3,
            raw_text=first.raw_text,
            is_search_representative=True,
        ),
        ChunkContext(
            chunk_id=second.candidate.chunk_id,
            document_id=second.candidate.document_id,
            version_id=second.candidate.version_id,
            parent_chunk_id=None,
            chunk_index=1,
            page_number=2,
            section_path=(),
            token_count=3,
            raw_text=second.raw_text,
            is_search_representative=True,
        ),
    )

    def fail(
        _query: str,
        _pool: tuple[RerankPassage, ...],
        _deadline: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Simulate a schema failure.

        Args:
            _query: Unused.
            _pool: Unused.
            _deadline: Unused.

        Returns:
            Empty rankings with schema invalid.
        """

        return (), None, RerankFallbackReason.SCHEMA_INVALID

    profile = next(
        case.expected_profile
        for case in load_open_splits()
        if case.query_class is QueryClass.SEMANTIC_FACTUAL
    )
    selected = select_hybrid_context(
        query="how does retention work",
        profile=profile,
        fused=fused,
        contexts=contexts,
        channel_hits={
            first.candidate.chunk_id: frozenset({"dense"}),
            second.candidate.chunk_id: frozenset({"dense"}),
        },
        rerank=fail,
        load_context=lambda _ids: (),
        remaining_deadline_seconds=8.0,
    )
    assert selected.fallback_reason is RerankFallbackReason.SCHEMA_INVALID
    assert selected.rerank_order == (
        first.candidate.chunk_id,
        second.candidate.chunk_id,
    )
    assert selected.usage is None


def test_mmr_respects_document_quota() -> None:
    """A single document cannot fill the final context under quota 1."""

    document = uuid4()
    first = _passage(document=document, text="leave policy annual days")
    second = _passage(document=document, text="leave policy annual days copy")
    third = _passage(text="unrelated procurement vendor terms")
    selected, dropped = apply_mmr(
        (first, second, third),
        query="leave policy",
        document_quota=1,
        limit=3,
    )
    docs = {item.candidate.document_id for item in selected}
    assert document in docs
    assert (
        len([item for item in selected if item.candidate.document_id == document]) == 1
    )
    assert third.candidate.chunk_id in {item.candidate.chunk_id for item in selected}
    assert second.candidate.chunk_id in set(dropped) or first.candidate.chunk_id in set(
        dropped
    )


def test_parent_expansion_rechecks_and_drops_stale() -> None:
    """Parents are loaded through the recheck callback; missing IDs stay out."""

    parent_id = uuid4()
    child = _passage(text="child passage", parent=parent_id)
    parent_ctx = ChunkContext(
        chunk_id=parent_id,
        document_id=child.candidate.document_id,
        version_id=child.candidate.version_id,
        parent_chunk_id=None,
        chunk_index=0,
        page_number=1,
        section_path=("Overview",),
        token_count=2,
        raw_text="parent heading overview",
        is_search_representative=False,
    )

    def load(ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Return the parent only when requested.

        Args:
            ids: Requested parent IDs.

        Returns:
            Parent context or empty when the ID is stale.
        """

        if parent_id in ids:
            return (parent_ctx,)
        return ()

    expanded, parent_ids = expand_parents((child,), load)
    assert parent_id in parent_ids
    assert len(expanded) == 2
    stale_child = _passage(text="orphan", parent=uuid4())
    empty, empty_ids = expand_parents((stale_child,), lambda _ids: ())
    assert empty_ids == ()
    assert len(empty) == 1
    version = uuid4()
    document = uuid4()
    left = RerankPassage(
        candidate=RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=document,
            version_id=version,
            channel_rank=1,
            channel_score=1.0,
        ),
        raw_text="left neighbor",
        chunk_index=4,
        token_count=2,
        channels=frozenset({"dense"}),
        excerpt="left neighbor",
    )
    right = RerankPassage(
        candidate=RetrievalCandidate(
            chunk_id=uuid4(),
            document_id=document,
            version_id=version,
            channel_rank=2,
            channel_score=0.9,
        ),
        raw_text="right neighbor",
        chunk_index=5,
        token_count=2,
        channels=frozenset({"dense"}),
        excerpt="right neighbor",
    )
    with_adjacent, _parents = expand_parents(
        (right,),
        lambda _ids: (),
        pool=(left, right),
    )
    assert {item.candidate.chunk_id for item in with_adjacent} == {
        left.candidate.chunk_id,
        right.candidate.chunk_id,
    }


def test_select_records_one_model_call() -> None:
    """Non-trivial pools call the reranker once."""

    profile = next(
        case.expected_profile
        for case in load_open_splits()
        if case.query_class is QueryClass.SEMANTIC_FACTUAL
    )
    first = _passage(text="retention logs")
    second = _passage(text="vendor terms")
    contexts = (
        ChunkContext(
            chunk_id=first.candidate.chunk_id,
            document_id=first.candidate.document_id,
            version_id=first.candidate.version_id,
            parent_chunk_id=None,
            chunk_index=0,
            page_number=None,
            section_path=(),
            token_count=2,
            raw_text=first.raw_text,
            is_search_representative=True,
        ),
        ChunkContext(
            chunk_id=second.candidate.chunk_id,
            document_id=second.candidate.document_id,
            version_id=second.candidate.version_id,
            parent_chunk_id=None,
            chunk_index=1,
            page_number=None,
            section_path=(),
            token_count=2,
            raw_text=second.raw_text,
            is_search_representative=True,
        ),
    )
    selected = select_hybrid_context(
        query=profile.original_query,
        profile=profile,
        fused=(first.candidate, second.candidate),
        contexts=contexts,
        channel_hits={
            first.candidate.chunk_id: frozenset({"dense"}),
            second.candidate.chunk_id: frozenset({"bm25"}),
        },
        rerank=_identity_rerank,
        load_context=lambda _ids: (),
        remaining_deadline_seconds=8.0,
    )
    assert selected.usage is not None
    assert selected.usage.model_calls == 1
    assert selected.fallback_reason is RerankFallbackReason.NONE


def test_no_local_rerank_runtime_in_lockfile() -> None:
    """Repository pins must not include a local cross-encoder runtime."""

    text = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    lock = Path("uv.lock").read_text(encoding="utf-8").lower()
    forbidden = (
        "sentence-transformers",
        "cross-encoder",
        "flashrank",
        "rerankers",
    )
    lock_forbidden = (*forbidden, "sentence_transformers")
    for name in forbidden:
        assert name not in text
    for name in lock_forbidden:
        assert name not in lock
    assert "torch" not in text
    assert "transformers" not in text
    assert "cohere" not in text


def test_counterfactual_script_does_not_read_holdout() -> None:
    """The offline rerank eval cannot materialize holdout labels."""

    source = Path("scripts/eval_rerank_counterfactual.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    dumped = ast.dump(tree)
    assert "HOLDOUT" not in dumped
    assert "load_holdout" not in dumped
    assert "load_open_splits" in dumped


def test_passages_from_context_drops_unauthorized() -> None:
    """Fused IDs without context never become rerank excerpts."""

    allowed = _candidate()
    leaked = _candidate()
    contexts = (
        ChunkContext(
            chunk_id=allowed.chunk_id,
            document_id=allowed.document_id,
            version_id=allowed.version_id,
            parent_chunk_id=None,
            chunk_index=0,
            page_number=None,
            section_path=(),
            token_count=1,
            raw_text="visible",
            is_search_representative=True,
        ),
    )
    passages = passages_from_context(
        (allowed, leaked),
        contexts,
        {allowed.chunk_id: frozenset({"dense"})},
    )
    assert [item.candidate.chunk_id for item in passages] == [allowed.chunk_id]


def test_trim_token_budget_drops_over_budget_units() -> None:
    """Parent expansion cannot exceed the 12-unit / 3500-token ceiling."""

    small = _passage(text="short")
    huge = _passage(text="huge")
    huge = RerankPassage(
        candidate=huge.candidate,
        raw_text=huge.raw_text,
        token_count=4000,
        channels=huge.channels,
        excerpt=huge.raw_text,
    )
    trimmed = trim_token_budget((small, huge), budget=3500, limit=12)
    assert [item.candidate.chunk_id for item in trimmed] == [small.candidate.chunk_id]
    empty = trim_token_budget((huge,), budget=3500, limit=12)
    assert empty == ()


def test_mock_gateway_rerank_preserves_identity_order() -> None:
    """Mock mode returns fused order without opening a provider socket."""

    first = _passage(text="alpha unique")
    second = _passage(text="beta unique")
    gateway = create_model_gateway(AgentSettings())
    rankings, usage, reason = rerank_pool(
        "how does retention work",
        (first, second),
        8.0,
        gateway=gateway,
        prompt_text=rerank_prompt_text(),
    )
    assert reason is RerankFallbackReason.NONE
    assert usage is not None
    assert usage.model_calls == 1
    assert [item.chunk_id for item in rankings] == [
        first.candidate.chunk_id,
        second.candidate.chunk_id,
    ]


def test_budget_denied_does_not_call_gateway() -> None:
    """A zero remaining deadline falls back before any model call."""

    first = _passage(text="alpha unique")
    second = _passage(text="beta unique")
    rankings, usage, reason = rerank_pool(
        "how does retention work",
        (first, second),
        0.0,
        gateway=create_model_gateway(AgentSettings()),
        prompt_text=rerank_prompt_text(),
    )
    assert rankings == ()
    assert usage is None
    assert reason is RerankFallbackReason.BUDGET_DENIED


def test_invalid_json_schema_falls_back_to_rrf() -> None:
    """Invalid JSON from the model is a typed schema fallback, not success."""

    first = _passage(text="alpha unique")
    second = _passage(text="beta unique")

    class _Gateway:
        """Raise a typed schema-invalid rerank error."""

        async def generate_rerank(self, request: object) -> object:
            """Abort with invalid JSON.

            Args:
                request: Unused.

            Raises:
                OpenAIRerankError: Always schema invalid.
            """

            del request
            raise OpenAIRerankError("rerank_schema_invalid")

    rankings, usage, reason = rerank_pool(
        "how does retention work",
        (first, second),
        8.0,
        gateway=_Gateway(),  # type: ignore[arg-type]
        prompt_text=rerank_prompt_text(),
    )
    assert rankings == ()
    assert usage is None
    assert reason is RerankFallbackReason.SCHEMA_INVALID
