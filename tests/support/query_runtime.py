"""Authorized query-runtime builders shared by routing tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole


def authorized_runtime(
    family: Phase6RouteFamily = Phase6RouteFamily.COMPOSITE,
) -> AuthorizedRuntimeContext:
    """Return a packet 1 context with a Composite envelope unless overridden.

    Args:
        family: Reserved envelope family.

    Returns:
        Frozen authorized runtime context.
    """

    now = datetime.now(UTC)
    ceilings = {
        Phase6RouteFamily.HYBRID: (25, 7, 4, Decimal("2.80")),
        Phase6RouteFamily.COMBINED: (45, 8, 4, Decimal("3.20")),
        Phase6RouteFamily.STRUCTURED_TABLE: (30, 6, 4, Decimal("2.40")),
        Phase6RouteFamily.COMPOSITE: (50, 9, 5, Decimal("3.60")),
        Phase6RouteFamily.GRAPH_INSPECTION: (10, 3, 4, Decimal("0.75")),
        Phase6RouteFamily.NO_RETRIEVAL: (25, 7, 4, Decimal("2.80")),
        Phase6RouteFamily.SCOPED_REFUSAL: (25, 7, 4, Decimal("2.80")),
    }
    deadline, calls, tools, usd = ceilings[family]
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=family,
        deadline_at=now + timedelta(seconds=deadline),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=calls,
        tool_ceiling=tools,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=usd,
        remaining_usd=usd,
        remaining_prompt_tokens=calls * 8000,
        remaining_completion_tokens=calls * 2000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="b" * 64,
        status="pending",
    )
