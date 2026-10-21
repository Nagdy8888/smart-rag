"""Unit tests for server-owned query route ceilings and exhaustion helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from smart_rag_api.services.query_admission import query_admission_bucket_key
from smart_rag_core.query_admission.ceilings import (
    DEFAULT_MONTHLY_LLM_BUDGET_USD,
    MAX_CONCURRENT_QUERY_RUNS,
    RECURSION_LIMIT,
    QueryRetrieveBudget,
    assert_call_available,
    assert_correction_available,
    assert_deadline_open,
    assert_discovery_available,
    assert_manifest_available,
    assert_recursion_available,
    assert_retrieve_kind_available,
    assert_side_effect_available,
    assert_subquestion_available,
    assert_tool_available,
    debit_retrieve_budget,
    envelope_for_family,
    usage_kind_caps,
)
from smart_rag_core.query_admission.context import (
    AuthorizedRuntimeContext,
    requested_search_scope_from_row,
)
from smart_rag_core.query_admission.exceptions import (
    QueryBudgetError,
    QueryCeilingError,
)
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.identity import UserRole


def test_signed_monthly_and_concurrency_defaults() -> None:
    """QT-COST-001 and QT-CAP-004 remain the signed numeric sources."""

    assert DEFAULT_MONTHLY_LLM_BUDGET_USD == Decimal("200.00")
    assert MAX_CONCURRENT_QUERY_RUNS == 5
    assert RECURSION_LIMIT == 24


@pytest.mark.parametrize(
    ("family", "deadline", "calls", "tools", "usd"),
    [
        (Phase6RouteFamily.HYBRID, 25, 7, 4, Decimal("2.80")),
        (Phase6RouteFamily.COMBINED, 45, 8, 4, Decimal("3.20")),
        (Phase6RouteFamily.STRUCTURED_TABLE, 30, 6, 4, Decimal("2.40")),
        (Phase6RouteFamily.COMPOSITE, 75, 9, 5, Decimal("3.60")),
        (Phase6RouteFamily.GRAPH_INSPECTION, 10, 3, 4, Decimal("0.75")),
        (Phase6RouteFamily.NO_RETRIEVAL, 25, 7, 4, Decimal("2.80")),
        (Phase6RouteFamily.SCOPED_REFUSAL, 25, 7, 4, Decimal("2.80")),
        (Phase6RouteFamily.WEB_RESEARCH, 50, 5, 5, Decimal("2.00")),
    ],
)
def test_route_envelopes_match_quality_targets(
    family: Phase6RouteFamily,
    deadline: int,
    calls: int,
    tools: int,
    usd: Decimal,
) -> None:
    """Every family uses the signed deadline/call/tool table and derived USD."""

    ceiling = envelope_for_family(family)
    assert ceiling.deadline_seconds == deadline
    assert ceiling.model_call_ceiling == calls
    assert ceiling.tool_ceiling == tools
    assert ceiling.envelope_usd == usd
    assert ceiling.recursion_limit == 24
    expected_correction = 0 if family is Phase6RouteFamily.WEB_RESEARCH else 1
    assert ceiling.correction_ceiling == expected_correction
    assert ceiling.subquestion_ceiling == 3
    assert ceiling.discovery_ceiling == 1
    assert ceiling.manifest_ceiling == 3
    assert ceiling.side_effect_ceiling == 1
    assert ceiling.envelope_usd == ceiling.per_call_usd_cap * calls


def test_web_research_envelope_fits_inside_composite() -> None:
    """Forced Web 50s/5/5/2.00 stays inside Composite 50s/9/5/3.60."""

    web = envelope_for_family(Phase6RouteFamily.WEB_RESEARCH)
    composite = envelope_for_family(Phase6RouteFamily.COMPOSITE)
    assert web.deadline_seconds <= composite.deadline_seconds
    assert web.model_call_ceiling <= composite.model_call_ceiling
    assert web.tool_ceiling <= composite.tool_ceiling
    assert web.envelope_usd <= composite.envelope_usd
    assert web.envelope_prompt_tokens <= composite.envelope_prompt_tokens
    assert web.envelope_completion_tokens <= composite.envelope_completion_tokens
    assert web.correction_ceiling == 0


def test_client_usd_cannot_enlarge_hybrid_envelope() -> None:
    """A client-supplied amount is not an input to the ceiling table."""

    hybrid = envelope_for_family(Phase6RouteFamily.HYBRID)
    composite = envelope_for_family(Phase6RouteFamily.COMPOSITE)
    assert hybrid.envelope_usd < composite.envelope_usd
    assert hybrid.envelope_usd == Decimal("2.80")


def test_deadline_and_counter_exhaustion_fail_closed() -> None:
    """Overrun helpers terminate without fabricating success."""

    now = datetime(2026, 8, 16, tzinfo=UTC)
    with pytest.raises(QueryCeilingError, match="deadline_exhausted"):
        assert_deadline_open(now=now, deadline_at=now)
    with pytest.raises(QueryCeilingError, match="model_call_exhausted"):
        assert_call_available(0)
    with pytest.raises(QueryCeilingError, match="tool_exhausted"):
        assert_tool_available(0)
    with pytest.raises(QueryCeilingError, match="discovery_exhausted"):
        assert_discovery_available(0)
    with pytest.raises(QueryCeilingError, match="manifest_exhausted"):
        assert_manifest_available(0)
    with pytest.raises(QueryCeilingError, match="side_effect_exhausted"):
        assert_side_effect_available(0)
    with pytest.raises(QueryCeilingError, match="recursion_exhausted"):
        assert_recursion_available(0)
    with pytest.raises(QueryCeilingError, match="correction_exhausted"):
        assert_correction_available(0)
    with pytest.raises(QueryCeilingError, match="subquestion_exhausted"):
        assert_subquestion_available(0)

    assert_deadline_open(now=now, deadline_at=now + timedelta(seconds=1))
    assert assert_call_available(1) == 0
    assert assert_tool_available(1) == 0


def test_usage_kind_caps_are_allow_listed() -> None:
    """Unknown usage kinds cannot enlarge the per-call cap table."""

    usd, prompt, completion = usage_kind_caps("answer")
    assert usd == Decimal("0.40")
    assert prompt == 8000
    assert completion == 2000
    with pytest.raises(QueryCeilingError, match="unknown_usage_kind"):
        usage_kind_caps("client_unlimited")


def test_payload_hash_changes_with_message_not_with_key() -> None:
    """Idempotency key is not part of the payload hash."""

    from uuid import uuid4

    conversation_id = uuid4()
    first = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello",
        requested_search_scope=RequestedSearchScope.AUTO,
    )
    second = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello",
        requested_search_scope=RequestedSearchScope.AUTO,
    )
    changed = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello!",
        requested_search_scope=RequestedSearchScope.AUTO,
    )
    omitted = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello",
    )
    company = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello",
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    general = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello",
        requested_search_scope=RequestedSearchScope.GENERAL_KNOWLEDGE,
    )
    assert first == second
    assert first == omitted
    assert len(first) == 64
    assert first != changed
    assert first != company
    assert company != general
    web = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.WEB_RESEARCH,
        message="hello",
        requested_search_scope=RequestedSearchScope.WEB,
    )
    assert first != web
    assert company != web


def test_legacy_runtime_mapping_defaults_requested_scope_auto() -> None:
    """Old authorized-runtime mappings without scope become Auto."""

    now = datetime.now(UTC)
    context = AuthorizedRuntimeContext(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=UUID("22222222-2222-4222-8222-222222222222"),
        run_id=UUID("33333333-3333-4333-8333-333333333333"),
        reservation_id=UUID("44444444-4444-4444-8444-444444444444"),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
        deadline_at=now + timedelta(seconds=50),
        recursion_limit=8,
        correction_ceiling=1,
        subquestion_ceiling=0,
        model_call_ceiling=8,
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
    dumped = context.model_dump(mode="json")
    dumped.pop("requested_search_scope")
    restored = AuthorizedRuntimeContext.from_mapping(dumped)
    assert restored.requested_search_scope is RequestedSearchScope.AUTO
    round_trip = AuthorizedRuntimeContext.from_mapping(context.model_dump(mode="json"))
    assert round_trip.requested_search_scope is RequestedSearchScope.COMPANY_DOCUMENTS
    assert requested_search_scope_from_row(None) is RequestedSearchScope.AUTO
    with pytest.raises(ValueError):
        requested_search_scope_from_row("world_knowledge")


def test_query_admission_bucket_includes_user_id() -> None:
    """FastAPI limiter buckets are user-scoped and not Valkey authority."""

    user_id = "11111111-1111-1111-1111-111111111111"
    assert query_admission_bucket_key(user_id) == f"query-admission:{user_id}"


def test_retrieve_kind_caps_fail_closed_when_remaining_cannot_cover() -> None:
    """Embed/rerank/lightrag must not run when remaining USD or calls are gone."""

    usd, prompt, completion = assert_retrieve_kind_available(
        remaining_model_calls=4,
        remaining_usd=Decimal("0.20"),
        usage_kind="rerank",
    )
    assert usd == Decimal("0.20")
    assert prompt == 12000
    assert completion == 2000
    with pytest.raises(QueryCeilingError, match="answer_stage_reserve_exhausted"):
        assert_retrieve_kind_available(
            remaining_model_calls=2,
            remaining_usd=Decimal("0.20"),
            usage_kind="rerank",
        )
    with pytest.raises(QueryBudgetError, match="reservation_exhausted"):
        assert_retrieve_kind_available(
            remaining_model_calls=7,
            remaining_usd=Decimal("0.10"),
            usage_kind="rerank",
        )
    with pytest.raises(QueryCeilingError, match="model_call_exhausted"):
        assert_retrieve_kind_available(
            remaining_model_calls=0,
            remaining_usd=Decimal("2.80"),
            usage_kind="embedding",
        )


def test_debit_retrieve_budget_decrements_remaining() -> None:
    """In-memory retrieve debit records usage kinds and remaining."""

    budget = QueryRetrieveBudget(
        remaining_model_calls=7,
        remaining_usd=Decimal("2.80"),
    )
    debit_retrieve_budget(budget, "embedding")
    debit_retrieve_budget(budget, "rerank")
    assert budget.usage_kinds == ["embedding", "rerank"]
    assert budget.remaining_model_calls == 5
    assert budget.remaining_usd == Decimal("2.58")
