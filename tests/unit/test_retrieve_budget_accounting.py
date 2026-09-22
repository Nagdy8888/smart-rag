"""Retrieve-time durable accounting and rerank time reserve."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_agents.query.nodes.shared import retrieve_budget
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.gateways.embedding import EmbeddingResponse
from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_admission.exceptions import QueryBudgetError
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_admission.usage_caps import ANSWER_STAGE_MIN_SECONDS
from smart_rag_core.retrieval.context import select_hybrid_context
from smart_rag_core.retrieval.context_loader import ChunkContext
from smart_rag_core.retrieval.hybrid_run.budget import counted_retrieve_send
from smart_rag_core.retrieval.profiles import RERANK_RESERVED_SECONDS
from smart_rag_core.retrieval.rerank import (
    RerankFallbackReason,
    RerankPassage,
    RerankRanking,
    RerankUsage,
)
from smart_rag_core.retrieval.types import RetrievalCandidate
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.support.query_runtime import authorized_runtime


class _FakeAppApiConnection(psycopg.Connection):
    """Subclass used so ``isinstance(..., psycopg.Connection)`` holds."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Skip libpq connect.

        Args:
            *args: Unused positional Connection arguments.
            **kwargs: Unused keyword Connection arguments.
        """

        del args, kwargs


def _caller() -> CallerContext:
    """Return a member caller for counted retrieve tests.

    Returns:
        Frozen caller context.
    """

    return CallerContext(
        user_id="00000000-0000-0000-0000-000000000099",
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _candidate() -> RetrievalCandidate:
    """Build one fused candidate.

    Returns:
        Frozen candidate with new UUIDs.
    """

    return RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )


def test_counted_retrieve_send_fails_closed_without_connection() -> None:
    """A bound run must not skip durable ``llm_usage`` writes."""

    budget = QueryRetrieveBudget(
        remaining_model_calls=6,
        remaining_usd=Decimal("1.00"),
        caller=_caller(),
        run_id=uuid4(),
        reservation_id=uuid4(),
    )
    with pytest.raises(
        QueryBudgetError, match="retrieve_accounting_connection_missing"
    ):
        counted_retrieve_send(
            budget,
            usage_kind="embedding",
            model_id="text-embedding-3-large",
            send=lambda: None,
        )
    assert budget.usage_kinds == []


def test_counted_retrieve_send_writes_durable_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding sends persist through ``execute_counted_model_call``."""

    recorded: dict[str, object] = {}
    response = EmbeddingResponse(
        mode="openai",
        vectors=((0.0, 1.0),),
        provider_request_id="req-1",
        fixture_provenance="openai://embeddings/test",
        estimated_cost_usd=Decimal("0.001"),
        prompt_tokens=17,
    )
    consume = ReservationConsumeResult(
        reservation_id=UUID("00000000-0000-0000-0000-000000000001"),
        optimistic_version=2,
        remaining_usd=Decimal("0.98"),
        remaining_prompt_tokens=10_000,
        remaining_completion_tokens=10_000,
    )

    def _fake_execute(*args: object, **kwargs: object) -> tuple[object, object, UUID]:
        """Capture durable consume kwargs and return the send result.

        Args:
            *args: Unused positional arguments.
            **kwargs: Counted-call fields including ``send``.

        Returns:
            Provider result, consume snapshot, and usage id.
        """

        del args
        recorded.update(kwargs)
        send = kwargs["send"]
        assert callable(send)
        return send(), consume, uuid4()

    monkeypatch.setattr(
        "smart_rag_core.query_admission.usage.execute_counted_model_call",
        _fake_execute,
    )
    budget = QueryRetrieveBudget(
        remaining_model_calls=6,
        remaining_usd=Decimal("1.00"),
        connection=_FakeAppApiConnection(),
        caller=_caller(),
        run_id=uuid4(),
        reservation_id=uuid4(),
    )
    result = counted_retrieve_send(
        budget,
        usage_kind="embedding",
        model_id="text-embedding-3-large",
        send=lambda: response,
    )
    assert result is response
    assert recorded["usage_kind"] == "embedding"
    assert recorded["model_id"] == "text-embedding-3-large"
    assert budget.usage_kinds == ["embedding"]
    assert budget.prompt_tokens == 17
    assert budget.expected_version == 2
    assert budget.remaining_usd == Decimal("0.98")


def test_retrieve_budget_binds_run_connection() -> None:
    """Ask retrieve must copy the per-run ``app_api`` connection."""

    runtime = authorized_runtime()
    state = pending_query_state(runtime.model_dump(mode="json"))
    state["remaining_model_calls"] = 6
    connection = _FakeAppApiConnection()
    budget = retrieve_budget(state, runtime, connection=connection)
    assert budget.connection is connection
    assert budget.run_id == runtime.run_id
    assert budget.reservation_id == runtime.reservation_id


def test_rerank_reserve_is_inside_retrieval_slice_not_answer_stage() -> None:
    """Rerank time comes from the 10s retrieve slice, not the answer reserve."""

    assert RERANK_RESERVED_SECONDS == 3.0
    assert RERANK_RESERVED_SECONDS != ANSWER_STAGE_MIN_SECONDS
    assert ANSWER_STAGE_MIN_SECONDS == 8.0


def test_select_hybrid_context_skips_rerank_when_reserve_unmet() -> None:
    """Insufficient remaining slice records RRF timeout instead of OpenAI."""

    first = _candidate()
    second = _candidate()
    fused = (first, second)
    contexts = (
        ChunkContext(
            chunk_id=first.chunk_id,
            document_id=first.document_id,
            version_id=first.version_id,
            parent_chunk_id=None,
            chunk_index=0,
            page_number=1,
            section_path=(),
            token_count=3,
            raw_text="leave policy annual days",
            is_search_representative=True,
        ),
        ChunkContext(
            chunk_id=second.chunk_id,
            document_id=second.document_id,
            version_id=second.version_id,
            parent_chunk_id=None,
            chunk_index=1,
            page_number=2,
            section_path=(),
            token_count=3,
            raw_text="procurement vendor terms",
            is_search_representative=True,
        ),
    )

    def fail(
        _query: str,
        _pool: tuple[RerankPassage, ...],
        _deadline: float,
    ) -> tuple[tuple[RerankRanking, ...], RerankUsage | None, RerankFallbackReason]:
        """Provider rerank must not start when the reserve is unmet.

        Args:
            _query: Unused query.
            _pool: Unused pool.
            _deadline: Unused remaining seconds.

        Returns:
            Never returns; the test fails if this callback runs.
        """

        raise AssertionError("rerank must not start below the reserved envelope")

    selected = select_hybrid_context(
        query="leave policy",
        profile=None,
        fused=fused,
        contexts=contexts,
        channel_hits={
            first.chunk_id: frozenset({"dense"}),
            second.chunk_id: frozenset({"dense"}),
        },
        rerank=fail,
        load_context=lambda _ids: (),
        remaining_deadline_seconds=1.5,
    )
    assert selected.fallback_reason is RerankFallbackReason.TIMEOUT
    assert selected.usage is None
    assert selected.skipped_counterfactual is False
