"""Deterministic route-matrix fixtures and plan invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.query_routing.matrix import (
    compile_retrieval_plan,
)
from smart_rag_core.query_routing.models import (
    BranchKind,
    RetrievalPlan,
)
from smart_rag_core.query_routing.serde import preparation_from_state
from smart_rag_core.query_routing.signals import is_no_retrieval

from tests.fixtures.query_routing_matrix_cases import MATRIX_ROUTE_CASES
from tests.support.query_routing import routing_kinds, routing_plan, routing_prep
from tests.support.query_runtime import authorized_runtime as _runtime


@pytest.mark.parametrize(
    ("case_id", "query", "family", "required_kinds", "limitations"),
    MATRIX_ROUTE_CASES,
    ids=[item[0] for item in MATRIX_ROUTE_CASES],
)
def test_matrix_routes(
    case_id: str,
    query: str,
    family: Phase6RouteFamily,
    required_kinds: set[BranchKind],
    limitations: set[str],
) -> None:
    """Every listed route, limitation, mixed, and Composite case is deterministic."""

    del case_id
    plan = routing_plan(query)
    assert plan.effective_route is family
    assert required_kinds <= routing_kinds(plan)
    assert limitations <= set(plan.limitations)
    assert plan.catalog_llm_call_count == 0
    assert plan.prove_complement is False
    assert plan.branch_concurrency == BRANCH_CONCURRENCY
    if BranchKind.GRAPH_LOCAL in routing_kinds(
        plan
    ) or BranchKind.GRAPH_HYBRID in routing_kinds(plan):
        assert "temporal_graph_limitation" not in plan.limitations
    if family is Phase6RouteFamily.NO_RETRIEVAL:
        assert plan.company_claim_forbidden is True
        assert plan.no_retrieval_answer_mode is not None
        assert BranchKind.HYBRID not in routing_kinds(plan)
        assert BranchKind.GRAPH_LOCAL not in routing_kinds(plan)
        assert BranchKind.STRUCTURED_TABLE not in routing_kinds(plan)
    else:
        assert plan.knowledge_scope is KnowledgeScope.COMPANY_DOCUMENTS
        assert plan.no_retrieval_answer_mode is None


def test_historical_relationship_never_has_graph_branch() -> None:
    """Historical relationships stay Hybrid with temporal_graph_limitation."""

    plan = routing_plan(
        "Which team owns the widget after the handoff as of 2020-01-01?"
    )
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.temporal_graph_limitation is True
    assert plan.historical_relationship is True
    assert not (
        {
            BranchKind.GRAPH_LOCAL,
            BranchKind.GRAPH_HYBRID,
            BranchKind.GRAPH_GLOBAL_STEERING,
        }
        & routing_kinds(plan)
    )


def test_whole_document_requires_section_coverage_one() -> None:
    """Whole-document claims require exactly ``section_coverage_ratio=1.0``."""

    plan = routing_plan("Summarize document p4-src-0001")
    assert plan.whole_document_summary is True
    assert plan.section_coverage_required == WHOLE_DOCUMENT_SECTION_COVERAGE
    refused = compile_retrieval_plan(
        routing_prep("Summarize document p4-src-0001"),
        _runtime(),
        section_coverage_ratio=0.5,
    )
    assert refused.effective_route is Phase6RouteFamily.SCOPED_REFUSAL
    assert "section_coverage_below_1" in refused.limitations


def test_negation_never_combined_or_complement() -> None:
    """Negation stays Hybrid and cannot prove a complement from top-k."""

    plan = routing_plan("What is not allowed for INV-SR-1001?")
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.prove_complement is False
    assert BranchKind.GRAPH_LOCAL not in routing_kinds(plan)
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate({**plan.model_dump(), "prove_complement": True})


def test_media_refusal_cannot_answer() -> None:
    """Unsupported media cannot become an answer family."""

    plan = routing_plan("Describe the unlabeled chart in the figure")
    assert plan.effective_route is Phase6RouteFamily.SCOPED_REFUSAL
    assert plan.media_answer_forbidden is True


def test_no_retrieval_forbids_company_claim() -> None:
    """NoRetrieval cannot make company-knowledge claims."""

    plan = routing_plan("Hello")
    assert plan.effective_route is Phase6RouteFamily.NO_RETRIEVAL
    assert plan.company_claim_forbidden is True
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(
            {**plan.model_dump(), "company_claim_forbidden": False}
        )


def test_greeting_prefix_does_not_hide_company_question() -> None:
    """A polite greeting prefix must not disable document retrieval."""

    assert is_no_retrieval("Hi!") is True
    assert is_no_retrieval("Hi, what is the documented refund policy?") is False


def test_graph_only_is_inspection_not_answer() -> None:
    """Graph-only remains inspection and cannot be an answer fallback."""

    plan = routing_plan("Inspect the current graph workspace")
    assert plan.effective_route is Phase6RouteFamily.GRAPH_INSPECTION
    assert plan.graph_as_answer_forbidden is True
    with pytest.raises(ValidationError):
        RetrievalPlan.model_validate(
            {**plan.model_dump(), "graph_as_answer_forbidden": False}
        )


def test_caption_media_may_use_hybrid() -> None:
    """Caption/OCR language lets a media query take ordinary Hybrid."""

    plan = routing_plan("What does the caption say under the unlabeled figure?")
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.media_answer_forbidden is False


def test_client_combined_cannot_enlarge_hybrid_reservation() -> None:
    """A Combined matrix result cannot enlarge a Hybrid reservation."""

    plan = compile_retrieval_plan(
        routing_prep("Which team owns INV-SR-1001 related to procurement?"),
        _runtime(Phase6RouteFamily.HYBRID),
    )
    assert plan.requested_route is Phase6RouteFamily.HYBRID
    assert plan.effective_route is Phase6RouteFamily.HYBRID
    assert plan.fallback_reason == "envelope_cannot_enlarge"
    assert BranchKind.GRAPH_LOCAL not in routing_kinds(plan)


def test_production_manual_override_rejected() -> None:
    """Production surfaces reject client manual routing."""

    with pytest.raises(QueryRoutingError, match="production_manual_override"):
        compile_retrieval_plan(
            routing_prep("What is the status of INV-SR-1001?"),
            _runtime(),
            requested_manual_route="combined",
        )


def test_fourth_subquestion_rejected() -> None:
    """A fourth subquestion fails closed instead of silently truncating."""

    prep = routing_prep("Compare PRJ-ALPHA leave days and notice period.")
    with pytest.raises(ValidationError):
        preparation_from_state(
            {
                **prep.model_dump(mode="json"),
                "decomposition": (
                    "one",
                    "two",
                    "three",
                    "four",
                ),
            }
        )
