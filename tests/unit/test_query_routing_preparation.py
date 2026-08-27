"""Preparation unit behavior for the deterministic route matrix."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from smart_rag_core.evaluation.classes import QueryClass
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branches import (
    disclose_acl_blindness,
    empty_keyword_guard,
    execute_branches,
    suppress_unauthorized_blindness,
)
from smart_rag_core.query_routing.constants import (
    PROVISIONAL_COVERAGE_THRESHOLD,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.matrix import (
    compile_retrieval_plan,
    frozen_coverage_threshold,
)
from smart_rag_core.query_routing.models import (
    REQUIRED_PREPARATION_FIELDS,
    BranchKind,
    QueryPreparation,
    RetrievalPlan,
)
from smart_rag_core.query_routing.preparation import (
    forbid_separate_rewrite_call,
    prepare_query,
)
from smart_rag_core.query_routing.serde import preparation_from_state
from smart_rag_core.retrieval.frozen_profile import (
    COVERAGE_SCORE_BASELINE,
    coverage_threshold_for,
)
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.support.query_routing import routing_plan, routing_prep
from tests.support.query_runtime import authorized_runtime as _runtime


def test_preparation_contains_every_required_field() -> None:
    """One typed preparation result contains every required field."""

    prep = routing_prep("What is the status of INV-SR-1001?")
    dumped = prep.model_dump()
    assert REQUIRED_PREPARATION_FIELDS <= set(dumped)
    assert prep.original == prep.original_fallback_variant
    assert prep.model_calls == 0
    assert prep.timezone == "UTC"
    assert prep.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
    assert "knowledge_scope" in REQUIRED_PREPARATION_FIELDS


def test_profile_schema_omission_fails() -> None:
    """Omitting a required preparation field is a schema failure."""

    with pytest.raises(ValidationError):
        QueryPreparation.model_validate({"original": "hi"})


def test_original_query_loss_fails() -> None:
    """The original query cannot be replaced by the rewrite fallback."""

    prep = routing_prep("What is the status of INV-SR-1001?")
    with pytest.raises(ValidationError):
        preparation_from_state(
            {**prep.model_dump(mode="json"), "original_fallback_variant": "rewritten"}
        )


def test_separate_rewrite_call_forbidden() -> None:
    """A second standalone rewrite call is forbidden."""

    with pytest.raises(QueryRoutingError, match="separate_rewrite_call"):
        forbid_separate_rewrite_call()


def test_model_assisted_prep_uses_at_most_one_call() -> None:
    """Rewrite plus profile share one structured call and keep fidelity."""

    calls = {"n": 0}

    def _caller(query: str, memory: object) -> object:
        """Count one preparation model call.

        Args:
            query: User query.
            memory: Unused memory snapshot.

        Returns:
            A preparation payload that keeps the entity token.
        """

        del memory
        calls["n"] += 1
        from smart_rag_core.query_routing.models import PreparationModelPayload

        return PreparationModelPayload(
            rewrite=query + " please",
            confidence=0.8,
            hl_keywords=("status",),
            ll_keywords=("INV-SR-1001",),
        )

    prep = prepare_query(
        "What is the status of INV-SR-1001?",
        runtime=_runtime(),
        model_caller=_caller,  # pyright: ignore[reportArgumentType]
        force_model=True,
    )
    assert calls["n"] == 1
    assert prep.model_calls == 1
    assert prep.original == "What is the status of INV-SR-1001?"
    assert prep.intent_fidelity > 0.0
    assert prep.entity_fidelity == 1.0
    assert prep.rewrite is not None


def test_rewrite_dropping_entity_keeps_original() -> None:
    """A rewrite that drops codes is discarded; original remains the fallback."""

    def _caller(query: str, memory: object) -> object:
        """Return a rewrite that drops the invoice code.

        Args:
            query: Unused original query.
            memory: Unused memory snapshot.

        Returns:
            A preparation payload without the code token.
        """

        del query, memory
        from smart_rag_core.query_routing.models import PreparationModelPayload

        return PreparationModelPayload(rewrite="status of the invoice", confidence=0.9)

    prep = prepare_query(
        "What is the status of INV-SR-1001?",
        runtime=_runtime(),
        model_caller=_caller,  # pyright: ignore[reportArgumentType]
        force_model=True,
    )
    assert prep.rewrite is None
    assert prep.original_fallback_variant == prep.original
    assert prep.entity_fidelity < 1.0


def test_coverage_threshold_not_retuned() -> None:
    """Phase 6 does not retune the frozen 0.65 coverage threshold."""

    assert COVERAGE_SCORE_BASELINE == 0.65
    assert PROVISIONAL_COVERAGE_THRESHOLD == 0.65
    for query_class in QueryClass:
        assert coverage_threshold_for(query_class) == pytest.approx(0.65)
    prep = routing_prep("What is the status of INV-SR-1001?")
    assert frozen_coverage_threshold(prep) == pytest.approx(0.65)
    plan = routing_plan("What is the status of INV-SR-1001?")
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate({**plan.model_dump(), "coverage_threshold": 0.40})
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(
            {**plan.model_dump(), "section_coverage_required": 0.65}
        )


def test_empty_keywords_never_extract() -> None:
    """Empty graph keywords fail closed instead of a hidden extract call."""

    with pytest.raises(QueryRoutingError, match="empty_keywords"):
        empty_keyword_guard((), ("entity",))
    with pytest.raises(QueryRoutingError, match="empty_keywords"):
        empty_keyword_guard(("topic",), ())


def test_unauthorized_blindness_suppressed() -> None:
    """Unauthorized callers receive silence, not a revealing zero."""

    caller = CallerContext(
        user_id=str(uuid4()),
        role=UserRole.VIEWER,
        authorization_version=1,
    )
    assert (
        disclose_acl_blindness(caller=caller, count=7, authorized_visibility=False)
        is None
    )
    assert suppress_unauthorized_blindness(role=UserRole.VIEWER, count=7) is None
    assert (
        disclose_acl_blindness(caller=caller, count=7, authorized_visibility=True) == 7
    )


def test_branch_fan_out_rejected() -> None:
    """Server concurrency cannot be raised above two."""

    plan = routing_plan("What is the status of INV-SR-1001?")
    prep = routing_prep("What is the status of INV-SR-1001?")
    with pytest.raises(QueryRoutingError, match="branch_fan_out"):
        execute_branches(plan, prep, _runtime(), branch_concurrency=8)


def test_historical_execute_rejects_graph_path() -> None:
    """Executing a graph branch on a historical plan fails closed."""

    from smart_rag_core.query_routing.models import BranchSpec

    prep = routing_prep(
        "Which team owns the widget after the handoff as of 2020-01-01?"
    )
    plan = compile_retrieval_plan(prep, _runtime())
    poisoned = plan.model_copy(
        update={
            "branches": (
                BranchSpec(
                    branch_id="bad-graph",
                    kind=BranchKind.GRAPH_LOCAL,
                    family=Phase6RouteFamily.COMBINED,
                    query_text=prep.original,
                    parallel_group=0,
                    hl_keywords=("relationship_multi_hop",),
                    ll_keywords=("widget",),
                ),
            )
        }
    )
    with pytest.raises(QueryRoutingError, match="historical_graph_path"):
        execute_branches(poisoned, prep, _runtime())


def test_unbound_combined_degrades_without_graph_prose() -> None:
    """Missing LightRAG degrades Combined to Hybrid with graph_unavailable."""

    plan = routing_plan("Which team owns INV-SR-1001 related to procurement?")
    prep = routing_prep("Which team owns INV-SR-1001 related to procurement?")
    results = execute_branches(plan, prep, _runtime())
    graphish = [
        item
        for item in results
        if item.kind is BranchKind.HYBRID
        and item.fallback_reason == "graph_unavailable"
    ]
    assert graphish
    assert all(item.graph_prose_used is False for item in results)
    assert all(item.bm25_snippets_used is False for item in results)
    assert all(item.keyword_extract_count == 0 for item in results)
    assert all(
        item.run_id == results[0].run_id
        and item.reservation_id == results[0].reservation_id
        for item in results
    )
