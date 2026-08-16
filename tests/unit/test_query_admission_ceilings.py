"""Unit tests for server-owned query route ceilings and exhaustion helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from smart_rag_api.services.query_admission import query_admission_bucket_key
from smart_rag_core.query_admission.ceilings import (
    DEFAULT_MONTHLY_LLM_BUDGET_USD,
    MAX_CONCURRENT_QUERY_RUNS,
    RECURSION_LIMIT,
    assert_call_available,
    assert_correction_available,
    assert_deadline_open,
    assert_discovery_available,
    assert_manifest_available,
    assert_recursion_available,
    assert_side_effect_available,
    assert_subquestion_available,
    assert_tool_available,
    envelope_for_family,
    usage_kind_caps,
)
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily


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
        (Phase6RouteFamily.COMPOSITE, 50, 9, 5, Decimal("3.60")),
        (Phase6RouteFamily.GRAPH_INSPECTION, 10, 3, 4, Decimal("0.75")),
        (Phase6RouteFamily.NO_RETRIEVAL, 25, 7, 4, Decimal("2.80")),
        (Phase6RouteFamily.SCOPED_REFUSAL, 25, 7, 4, Decimal("2.80")),
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
    assert ceiling.correction_ceiling == 1
    assert ceiling.subquestion_ceiling == 3
    assert ceiling.discovery_ceiling == 1
    assert ceiling.manifest_ceiling == 3
    assert ceiling.side_effect_ceiling == 1
    assert ceiling.envelope_usd == ceiling.per_call_usd_cap * calls


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
    )
    second = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello",
    )
    changed = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="hello!",
    )
    assert first == second
    assert len(first) == 64
    assert first != changed


def test_query_admission_bucket_includes_user_id() -> None:
    """FastAPI limiter buckets are user-scoped and not Valkey authority."""

    user_id = "11111111-1111-1111-1111-111111111111"
    assert query_admission_bucket_key(user_id) == f"query-admission:{user_id}"
