"""LangGraph remaining_model_calls must follow retrieve consumes."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import smart_rag_core.retrieval.hybrid_run as _hybrid_run_cycle_guard  # noqa: F401
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.pipeline import execute_branches_node
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.security.identity import CallerContext

from tests.unit.test_query_routing_matrix import _runtime


class _DebitHybrid:
    """Hybrid double that spends two retrieve slots on the bound budget."""

    query_budget: QueryRetrieveBudget | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> object:
        """Debit two counted retrieve calls and return an empty Hybrid payload.

        Args:
            query: Unused.
            caller: Unused.
            profile: Unused.
            deadline_seconds: Unused.

        Returns:
            Namespace matching Hybrid fields used by branch execution.

        Raises:
            AssertionError: If execute_branches did not bind the ledger.
        """

        del query, caller, profile, deadline_seconds
        if self.query_budget is None:
            raise AssertionError("query_budget must be bound before retrieve")
        self.query_budget.remaining_model_calls -= 2
        return SimpleNamespace(
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


def test_execute_branches_uses_passed_remaining_not_ceiling() -> None:
    """Standalone retrieve must not reset remaining to the family ceiling."""

    runtime = _runtime(Phase6RouteFamily.HYBRID)
    query = "What is the status of INV-SR-1001?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    budget = QueryRetrieveBudget(
        remaining_model_calls=5,
        remaining_usd=Decimal("2.00"),
        caller=None,
        run_id=runtime.run_id,
        reservation_id=runtime.reservation_id,
        expected_version=runtime.optimistic_version,
    )
    execute_branches(
        plan,
        prep,
        runtime,
        hybrid_retriever=_DebitHybrid(),
        query_budget=budget,
    )
    assert budget.remaining_model_calls == 3
    assert runtime.model_call_ceiling == 7


def test_execute_branches_node_writes_remaining_model_calls() -> None:
    """Answer/verifier nodes must see remaining after retrieve, not after profile only."""

    runtime = _runtime(Phase6RouteFamily.HYBRID)
    query = "What is the status of INV-SR-1001?"
    prep = prepare_query(query, runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    state = pending_query_state(
        runtime.model_dump(mode="json"),
        user_query=query,
    )
    state["status"] = "planned"
    state["preparation"] = prep.model_dump(mode="json")
    state["retrieval_plan"] = plan.model_dump(mode="json")
    state["remaining_model_calls"] = 6
    hybrid = _DebitHybrid()
    updated = execute_branches_node(state, QueryGraphDeps(hybrid_retriever=hybrid))
    assert updated["remaining_model_calls"] == 4
    assert updated["status"] == "branches_executed"
    assert hybrid.query_budget is not None
    assert hybrid.query_budget.remaining_model_calls == 4
