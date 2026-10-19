"""Q15-sized source fitting, exact duplicate drop, and answer-stage reserves."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from smart_rag_agents.prompts import answer_prompt_text
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.gateway.sync_bridge import run_coro
from smart_rag_agents.query.nodes.answer import generate_answer_node
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.gateways.model_types import (
    AnswerModelResponse,
    ModelInputBoundError,
)
from smart_rag_core.query_admission.ceilings import (
    ANSWER_STAGE_MIN_SECONDS,
    ANSWER_STAGE_RESERVED_MODEL_CALLS,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_answer.assembly import (
    INPUT_BOUND_REFUSAL_TEXT,
    assemble_source_records,
    fit_source_records,
)
from smart_rag_core.query_answer.exceptions import AnswerError
from smart_rag_core.query_answer.models import AnswerCitation, AnswerPayload
from smart_rag_core.query_answer.sanitize import filter_invented_ids
from smart_rag_core.query_fusion import fusion_config_hash
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.models import TableEvidenceRecord
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import UserRole

from tests.support.query_runtime import RefusingHybridRetriever


def _passage(*, index: int, text: str, document: str | None = None) -> ScoredPassage:
    """Build one fusion passage with a stable UUID-shaped id.

    Args:
        index: 1-based rank and id suffix.
        text: Canonical citation text.
        document: Optional document UUID suffix owner.

    Returns:
        Frozen scored passage.
    """

    suffix = f"{index:012d}"
    doc_suffix = document or suffix
    return ScoredPassage(
        chunk_id=f"00000000-0000-4000-8000-{suffix}",
        document_id=f"00000000-0000-4000-8001-{doc_suffix}",
        version_id=f"00000000-0000-4000-8002-{suffix}",
        citation_text=text,
        hybrid_rank=index,
        combined_score=1.0 / index,
        origin=PassageOrigin.HYBRID,
        graph_discovered_only=False,
    )


def _fusion(
    passages: tuple[ScoredPassage, ...], *, route: str = "hybrid"
) -> FusionResult:
    """Return Hybrid-effective fusion wrapping passages.

    Args:
        passages: Ordered canonical evidence.
        route: Server-derived effective route.

    Returns:
        Frozen fusion result.
    """

    return FusionResult(
        algorithm=FusionAlgorithm.RESOLVED_PATH_FUSION,
        config_hash=fusion_config_hash(FusionAlgorithm.RESOLVED_PATH_FUSION),
        requested_route=route,
        effective_route=route,
        evidence=passages,
        graph_discovered_only_ratio=0.0,
    )


def _q15_passages() -> tuple[ScoredPassage, ...]:
    """Nine distinct passages whose raw citation text exceeds 16,384 characters.

    Returns:
        Ordered passages sized like the live Q15 overflow.
    """

    return tuple(
        _passage(index=index, text=f"Q15 passage {index} " + ("A" * 2060))
        for index in range(1, 10)
    )


class _RecordingAnswerGateway:
    """Gateway that records the fitted request and reports completion usage."""

    def __init__(self) -> None:
        """Initialize empty request capture."""

        self.calls = 0
        self.last_query = ""
        self.last_records = ""
        self.last_chunk_ids: tuple[str, ...] = ()

    async def generate_answer(self, request: object) -> AnswerModelResponse:
        """Capture source records and return a complete fixture.

        Args:
            request: Structured answer request.

        Returns:
            Mock answer with non-zero completion tokens.
        """

        self.calls += 1
        self.last_query = str(getattr(request, "query", ""))
        self.last_records = str(getattr(request, "source_records", ""))
        self.last_chunk_ids = tuple(getattr(request, "chunk_ids", ()))
        return AnswerModelResponse(
            mode="mock",
            payload={
                "answer_text": "Counted answer from authorized evidence.",
                "citations": [],
                "atomic_links": [],
                "composed_conclusion": None,
                "table_citations": [],
                "status": "complete",
            },
            request_id="fitted-answer",
            input_tokens=12,
            output_tokens=7,
        )


def test_q15_sized_passages_fit_under_model_input_bound() -> None:
    """Nine oversized passages fit so query plus records stay within 16,384."""

    original = _fusion(_q15_passages())
    raw = assemble_source_records(original, ())
    assert len(raw) > 16_384
    query = "Compare the four approaches."
    fit = fit_source_records(
        user_query=query,
        fusion=original,
        tables=(),
        max_input_chars=16_384,
        route="hybrid",
    )
    assert original.evidence == _q15_passages()
    assert len(query + fit.records) <= 16_384
    assert fit.trim_reason == "answer_context_trimmed"
    assert fit.dropped_chunk_ids
    assert set(fit.included_chunk_ids).isdisjoint(fit.dropped_chunk_ids)


def test_twelve_passages_fit_under_32768_input_bound() -> None:
    """Twelve 1500-character passages stay inside the 32768 input bound."""

    passages = tuple(
        _passage(index=index, text=f"{index:04d}" + ("a" * 1496))
        for index in range(1, 13)
    )
    fusion = _fusion(passages)
    fit = fit_source_records(
        user_query="List the named items.",
        fusion=fusion,
        tables=(),
        max_input_chars=32_768,
        route="hybrid",
    )
    assert fit.trim_reason == ""
    assert fit.included_chunk_ids == tuple(item.chunk_id for item in passages)
    assert fit.dropped_chunk_ids == ()


def test_exact_normalized_duplicates_keep_highest_ranked() -> None:
    """Two chunk IDs with identical normalized text keep the first ranked ID."""

    first = _passage(index=1, text="Refund window is 30 days.")
    second = _passage(index=2, text="  Refund window is 30 DAYS. \n")
    fusion = _fusion((first, second))
    fit = fit_source_records(
        user_query="refund?",
        fusion=fusion,
        tables=(),
        max_input_chars=16_384,
    )
    assert fit.included_chunk_ids == (first.chunk_id,)
    assert fit.dropped_chunk_ids == (second.chunk_id,)
    assert fit.duplicate_drop_count == 1


def test_near_duplicate_text_is_retained() -> None:
    """Near-but-not-identical citation text is not fuzzy-dropped."""

    first = _passage(index=1, text="Refund window is 30 days.")
    second = _passage(index=2, text="Refund window is 31 days.")
    fusion = _fusion((first, second))
    fit = fit_source_records(
        user_query="refund?",
        fusion=fusion,
        tables=(),
        max_input_chars=16_384,
    )
    assert fit.included_chunk_ids == (first.chunk_id, second.chunk_id)
    assert fit.duplicate_drop_count == 0


def test_fitting_does_not_mutate_original_fusion() -> None:
    """Fitting returns a new fusion object and leaves the original evidence."""

    fusion = _fusion(_q15_passages())
    before = fusion.evidence
    fit = fit_source_records(
        user_query="overflow",
        fusion=fusion,
        tables=(),
        max_input_chars=16_384,
    )
    assert fusion.evidence is before
    assert fusion.evidence == before
    assert fit.fusion is not fusion
    assert len(fit.fusion.evidence) < len(fusion.evidence)


def test_dropped_ids_cannot_be_cited() -> None:
    """Citations for budget-dropped chunk IDs are stripped."""

    fusion = _fusion(_q15_passages())
    fit = fit_source_records(
        user_query="overflow",
        fusion=fusion,
        tables=(),
        max_input_chars=16_384,
    )
    dropped = fit.dropped_chunk_ids[0]
    payload = AnswerPayload(
        answer_text="Dropped citation should disappear.",
        citations=(AnswerCitation(chunk_id=dropped, span="A" * 12),),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    filtered = filter_invented_ids(payload, fit.fusion, fit.tables)
    assert filtered.citations == ()


def test_impossibly_small_budget_is_typed_refusal() -> None:
    """A bound smaller than one delimited block refuses without a gateway call."""

    fusion = _fusion((_passage(index=1, text="The refund period is 30 days."),))
    fit = fit_source_records(
        user_query="What is the refund period?",
        fusion=fusion,
        tables=(),
        max_input_chars=8,
    )
    assert fit.trim_reason == "input_bound_exceeded"
    assert fit.included_chunk_ids == ()
    gateway = _RecordingAnswerGateway()
    deps = QueryGraphDeps(
        hybrid_retriever=RefusingHybridRetriever(),
        model_gateway=gateway,
        answer_prompt_text=answer_prompt_text(),
        model_input_max_chars=8,
    )
    state = pending_query_state(user_query="What is the refund period?")
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 8
    state["fusion"] = fusion.model_dump(mode="json")
    out = generate_answer_node(state, deps)
    assert gateway.calls == 0
    assert out["status"] == "insufficient_evidence"
    assert out["detail"] == "input_bound_exceeded"
    payload = AnswerPayload.model_validate(out["answer"])
    assert payload.answer_text == INPUT_BOUND_REFUSAL_TEXT
    assert payload.status == "refused"
    assert out["status"] != "gateway_failed"


def test_structured_table_route_reserves_table_before_prose() -> None:
    """StructuredTable keeps the table block when lower-ranked prose overflows."""

    table = TableEvidenceRecord(
        table_id="00000000-0000-4000-8000-000000000099",
        version_id="00000000-0000-4000-8000-000000000098",
        document_id="00000000-0000-4000-8000-000000000097",
        source_ranges=("A1:B2",),
        operation="sum",
        rows=({"total": 4},),
    )
    huge = _passage(index=1, text="P" * 4000)
    fusion = _fusion((huge,), route="structured_table")
    fit = fit_source_records(
        user_query="total?",
        fusion=fusion,
        tables=(table,),
        max_input_chars=800,
        route="structured_table",
    )
    assert table.table_id in fit.included_table_ids
    assert huge.chunk_id in fit.dropped_chunk_ids


def test_q15_generate_calls_gateway_once_with_bounded_records() -> None:
    """The Q15-sized fixture calls the answer gateway once under the bound."""

    gateway = _RecordingAnswerGateway()
    deps = QueryGraphDeps(
        hybrid_retriever=RefusingHybridRetriever(),
        model_gateway=gateway,
        answer_prompt_text=answer_prompt_text(),
        model_input_max_chars=16_384,
    )
    query = "Compare the four approaches."
    state = pending_query_state(user_query=query)
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 8
    state["fusion"] = _fusion(_q15_passages()).model_dump(mode="json")
    out = generate_answer_node(state, deps)
    assert gateway.calls == 1
    assert len(gateway.last_query + gateway.last_records) <= 16_384
    assert out["completion_tokens"] == 7
    assert out["status"] not in {"gateway_failed"}
    assert out["detail"] != "empty_answer"
    diagnostics = out["answer_context_fit"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["trim_reason"] == "answer_context_trimmed"
    payload = AnswerPayload.model_validate(out["answer"])
    assert payload.answer_text.strip()
    dropped = cast(list[str], diagnostics["dropped_chunk_ids"])
    for dropped_id in dropped:
        assert dropped_id not in gateway.last_chunk_ids


def _runtime(*, deadline_at: datetime) -> dict[str, object]:
    """Return an authorized-runtime mapping with a controllable deadline.

    Args:
        deadline_at: Absolute UTC deadline.

    Returns:
        JSON-safe runtime mapping.
    """

    now = deadline_at - timedelta(seconds=25)
    context = AuthorizedRuntimeContext(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=UUID("22222222-2222-4222-8222-222222222222"),
        run_id=UUID("33333333-3333-4333-8333-333333333333"),
        reservation_id=UUID("44444444-4444-4444-8444-444444444444"),
        reconnect=False,
        route_family=Phase6RouteFamily.HYBRID,
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
        deadline_at=deadline_at,
        recursion_limit=8,
        correction_ceiling=1,
        subquestion_ceiling=0,
        model_call_ceiling=7,
        tool_ceiling=3,
        discovery_ceiling=0,
        manifest_ceiling=2,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("0.50"),
        remaining_usd=Decimal("0.50"),
        remaining_prompt_tokens=8000,
        remaining_completion_tokens=2000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="c" * 64,
        status="pending",
    )
    return context.model_dump(mode="json")


def test_deadline_reserve_skips_provider_and_never_empty_answer() -> None:
    """Less than eight remaining seconds skips the answer provider."""

    gateway = _RecordingAnswerGateway()
    frozen = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    deps = QueryGraphDeps(
        hybrid_retriever=RefusingHybridRetriever(),
        model_gateway=gateway,
        answer_prompt_text=answer_prompt_text(),
        now=lambda: frozen,
    )
    deadline = frozen + timedelta(seconds=ANSWER_STAGE_MIN_SECONDS - 1)
    state = pending_query_state(
        _runtime(deadline_at=deadline),
        user_query="What is the refund period?",
    )
    state["status"] = "optional_tools_resolved"
    state["remaining_model_calls"] = 8
    state["fusion"] = _fusion(
        (_passage(index=1, text="The refund period is 30 days."),)
    ).model_dump(mode="json")
    out = generate_answer_node(state, deps)
    assert gateway.calls == 0
    assert out["detail"] == "answer_deadline_reserve_exhausted"
    assert out["status"] == "verified_partial"
    payload = AnswerPayload.model_validate(out["answer"])
    assert payload.answer_text.strip()
    assert out["detail"] != "empty_answer"


def test_run_coro_maps_model_input_bound_error_without_string_matching() -> None:
    """``run_coro`` maps the typed overflow error, not ``gateway_failed``."""

    async def _boom() -> str:
        """Raise the typed input-bound error.

        Returns:
            Unreachable token.
        """

        raise ModelInputBoundError("Model input exceeds configured 4-character bound")

    try:
        run_coro(lambda: _boom())
    except AnswerError as exc:
        assert exc.reason == "input_bound_exceeded"
    else:
        raise AssertionError("expected input_bound_exceeded")


def test_answer_stage_reserve_constants() -> None:
    """Company answer plus verifier still consume two reserved calls."""

    assert ANSWER_STAGE_RESERVED_MODEL_CALLS == 3
    assert ANSWER_STAGE_MIN_SECONDS == 8.0
