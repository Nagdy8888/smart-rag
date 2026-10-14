"""Compile-once graph reuse with isolated per-run runtime context."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from smart_rag_agents.query.deps import QueryGraphContext, QueryGraphDeps
from smart_rag_agents.query.graph import compile_query_graph
from smart_rag_agents.query.state import pending_query_state
from smart_rag_agents.query.studio import graph as studio_graph
from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.support.typed_graph import untyped

_COMPANY_QUERY = "What is our refund period?"
_EMPTY_HYBRID = SimpleNamespace(
    ranked_ids=(UUID("00000000-0000-0000-0000-000000000001"),),
    evidence=(),
    coverage=SimpleNamespace(
        coverage_score=0.80,
        uncovered_headings=(),
        signal="ok",
        notes=(),
    ),
    fallback_reason="none",
)


class _TaggedHybrid:
    """Hybrid spy that records the run tag stored on this instance."""

    query_budget: QueryRetrieveBudget | None = None

    def __init__(self, tag: str) -> None:
        """Store one isolation tag.

        Args:
            tag: Unique label for this run's retriever.
        """

        self.tag = tag
        self.calls: list[str] = []

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
        **_kwargs: object,
    ) -> object:
        """Record a retrieve and return empty Hybrid-shaped evidence.

        Args:
            query: Unused branch query.
            caller: Unused caller.
            profile: Unused profile.
            deadline_seconds: Unused remaining slice.
            **_kwargs: Unused retrieve keywords such as cache mode.

        Returns:
            Empty authorized Hybrid payload so the run can refuse later.
        """

        del query, caller, profile, deadline_seconds, _kwargs
        self.calls.append(self.tag)
        return _EMPTY_HYBRID


def _runtime(*, run_id: object | None = None) -> AuthorizedRuntimeContext:
    """Build a Composite envelope for compile-reuse tests.

    Args:
        run_id: Optional run UUID.

    Returns:
        Frozen authorized context.
    """

    now = datetime.now(UTC)
    return AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=run_id if isinstance(run_id, UUID) else uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.COMPOSITE,
        deadline_at=now + timedelta(seconds=50),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=9,
        tool_ceiling=5,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("3.60"),
        remaining_usd=Decimal("3.60"),
        remaining_prompt_tokens=72000,
        remaining_completion_tokens=18000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="0" * 64,
        status="admitted",
    )


def _invoke_company(compiled: object, deps: QueryGraphDeps) -> str:
    """Invoke one company-document run on the process compiled graph.

    Args:
        compiled: Graph compiled once for the process cache.
        deps: Run-local deps injected through ``QueryGraphContext``.

    Returns:
        Terminal status string.
    """

    state = pending_query_state(
        _runtime().model_dump(mode="json"), user_query=_COMPANY_QUERY
    )
    invoke = untyped(compiled).invoke
    result = invoke(state, context=QueryGraphContext(deps=deps))
    if isinstance(result, dict):
        return str(cast(dict[str, object], result).get("status") or "missing")
    return "missing"


def test_two_concurrent_invokes_do_not_cross_deps() -> None:
    """One compiled graph plus two contexts keeps adapters isolated."""

    compiled = compile_query_graph()
    first_hybrid = _TaggedHybrid("run-a")
    second_hybrid = _TaggedHybrid("run-b")
    cancelled_hybrid = _TaggedHybrid("run-cancel")
    first_deps = QueryGraphDeps(hybrid_retriever=first_hybrid)
    second_deps = QueryGraphDeps(hybrid_retriever=second_hybrid)
    cancelled_deps = QueryGraphDeps(
        hybrid_retriever=cancelled_hybrid,
        cancel_check=lambda: True,
    )

    async def _run() -> tuple[str, str, str]:
        """Invoke two live runs and one cancelled run concurrently.

        Returns:
            Terminal statuses for the two live runs and the cancelled run.
        """

        return await asyncio.gather(
            asyncio.to_thread(_invoke_company, compiled, first_deps),
            asyncio.to_thread(_invoke_company, compiled, second_deps),
            asyncio.to_thread(_invoke_company, compiled, cancelled_deps),
        )

    first, second, cancelled = asyncio.run(_run())
    assert first != "missing"
    assert second != "missing"
    assert cancelled != "missing"
    assert first_hybrid.calls == ["run-a"]
    assert second_hybrid.calls == ["run-b"]
    assert cancelled_hybrid.calls == []


def test_studio_module_graph_stays_unbound() -> None:
    """Module-level Studio graph compiles without live adapters."""

    result = cast(dict[str, object], untyped(studio_graph).invoke({"user_query": "Hi"}))
    runtime = result.get("authorized_runtime")
    assert isinstance(runtime, dict)
    typed_runtime = cast(dict[str, object], runtime)
    assert typed_runtime.get("status") == "studio_local"
    assert result.get("answer") is not None or result.get("status") in {
        "admission_rejected",
        "verified",
        "answered",
        "verified_partial",
    }
