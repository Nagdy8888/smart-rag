"""LangGraph remaining holds must follow profile, retrieve, and answer consumes."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.answer import generate_answer_node
from smart_rag_agents.query.nodes.company_scope import execute_branches_node
from smart_rag_agents.query.nodes.prepare import prepare_query_node
from smart_rag_agents.query.nodes.shared import runtime_after_consume
from smart_rag_agents.query.state import pending_query_state
from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.service import ReservationConsumeResult
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.security.identity import CallerContext

from tests.support.query_runtime import authorized_runtime as _runtime


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
    written = AuthorizedRuntimeContext.from_mapping(updated["authorized_runtime"])
    assert written.optimistic_version == hybrid.query_budget.expected_version
    assert written.remaining_usd == hybrid.query_budget.remaining_usd


def test_runtime_after_consume_advances_optimistic_version() -> None:
    """A profile consume snapshot must not stay on admit version 1."""

    runtime = _runtime()
    consumed = ReservationConsumeResult(
        reservation_id=runtime.reservation_id,
        optimistic_version=2,
        remaining_usd=Decimal("3.52"),
        remaining_prompt_tokens=68000,
        remaining_completion_tokens=16500,
    )
    updated = runtime_after_consume(runtime, consumed)
    assert updated.optimistic_version == 2
    assert updated.remaining_usd == Decimal("3.52")
    assert updated.remaining_prompt_tokens == 68000
    assert updated.run_id == runtime.run_id


def test_prepare_query_node_writes_profile_reservation_version() -> None:
    """Greeting profile consume must land on authorized_runtime before answer."""

    runtime = _runtime()
    prep = prepare_query("hi friend", runtime=runtime)
    state = pending_query_state(
        runtime.model_dump(mode="json"),
        user_query="hi friend",
    )
    state["status"] = "memory_loaded"

    def _prepare(
        query: str,
        **kwargs: object,
    ) -> object:
        """Return a real preparation and emit one profile consume.

        Args:
            query: Unused original query.
            **kwargs: Must include ``on_reservation_consume``.

        Returns:
            Typed preparation for ``hi friend``.
        """

        del query
        hook = kwargs.get("on_reservation_consume")
        if callable(hook):
            hook(
                ReservationConsumeResult(
                    reservation_id=runtime.reservation_id,
                    optimistic_version=2,
                    remaining_usd=Decimal("3.52"),
                    remaining_prompt_tokens=68000,
                    remaining_completion_tokens=16500,
                )
            )
        return prep

    with patch("smart_rag_agents.query.nodes.prepare.prepare_query", _prepare):
        updated = prepare_query_node(state, QueryGraphDeps())
    written = AuthorizedRuntimeContext.from_mapping(updated["authorized_runtime"])
    assert written.optimistic_version == 2
    assert written.remaining_usd == Decimal("3.52")


def test_answer_consume_uses_runtime_version_after_profile() -> None:
    """The answer call must send the post-profile reservation version."""

    runtime = _runtime().model_copy(update={"optimistic_version": 2})
    prep = prepare_query("hi friend", runtime=runtime)
    plan = compile_retrieval_plan(prep, runtime)
    state = pending_query_state(
        runtime.model_dump(mode="json"),
        user_query="hi friend",
    )
    state["status"] = "planned"
    state["preparation"] = prep.model_dump(mode="json")
    state["retrieval_plan"] = plan.model_dump(mode="json")
    state["remaining_model_calls"] = 8
    seen: dict[str, int] = {}

    def _counted(*args: object, **kwargs: object) -> object:
        """Record the consume version and return a general greeting.

        Args:
            *args: Positional connection argument.
            **kwargs: ``execute_counted_model_call`` keywords.

        Returns:
            Payload, consume snapshot, and usage id.
        """

        del args
        seen["expected_version"] = int(str(kwargs["expected_version"]))
        payload = AnswerPayload(
            answer_text="Hello.",
            status="complete",
            answer_origin=KnowledgeScope.GENERAL_KNOWLEDGE,
        )
        consumed = ReservationConsumeResult(
            reservation_id=runtime.reservation_id,
            optimistic_version=3,
            remaining_usd=Decimal("3.12"),
            remaining_prompt_tokens=60000,
            remaining_completion_tokens=14500,
        )
        return (payload, 10, 4), consumed, uuid4()

    deps = QueryGraphDeps(
        model_gateway=SimpleNamespace(),
        general_chat_prompt_text="general",
        connection=SimpleNamespace(),
    )
    with patch(
        "smart_rag_agents.query.nodes.answer.execute_counted_model_call",
        _counted,
    ):
        updated = generate_answer_node(state, deps)
    assert seen["expected_version"] == 2
    written = AuthorizedRuntimeContext.from_mapping(updated["authorized_runtime"])
    assert written.optimistic_version == 3
    assert updated["status"] == "answered"
