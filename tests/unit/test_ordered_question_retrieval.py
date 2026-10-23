"""Explicit independent questions retain separate bounded retrieval branches."""

from collections.abc import Sequence

from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.models import (
    BranchKind,
    MemoryRecord,
    PreparationModelPayload,
)
from smart_rag_core.query_routing.preparation import (
    prepare_query,
    resolved_comparison_parts,
)
from smart_rag_core.search_scope import RequestedSearchScope

from tests.support.query_routing import routing_plan, routing_prep
from tests.support.query_runtime import authorized_runtime


def test_ordered_questions_retrieve_both_parts_without_a_model_call() -> None:
    """The first topic cannot consume every retrieval slot of the second."""
    query = "Using our documents, first explain queue retries; then describe durable storage tradeoffs."
    prep = routing_prep(query)
    assert prep.original == query
    assert prep.model_calls == 0
    assert prep.decomposition == (
        "explain queue retries",
        "describe durable storage tradeoffs.",
    )
    plan = routing_plan(query)
    hybrid = [b for b in plan.branches if b.kind is BranchKind.HYBRID]
    assert {b.query_text for b in hybrid} == set(prep.decomposition)
    assert all(b.inherit_run_id and b.inherit_reservation for b in hybrid)
    assert len(plan.branches) <= 4


def test_ordinary_explanation_does_not_gain_extra_retrieval() -> None:
    """The fallback is limited to explicit ordered question syntax."""
    assert routing_prep("Explain the first durable queue.").decomposition == ()


def test_resolved_difference_followup_retrieves_both_existing_operands() -> None:
    """A joint comparison query must not lose the less-common second source topic."""
    original = "How does that differ from checking an HTTP response status?"
    resolved = "How does validating tool-call inputs differ from checking an HTTP response status?"
    context = authorized_runtime()
    calls: list[str] = []

    def profile(
        question: str, memory: Sequence[MemoryRecord]
    ) -> PreparationModelPayload:
        """Resolve the existing comparison in the same preparation call."""
        calls.append(question)
        return PreparationModelPayload(rewrite=resolved)

    prepared = prepare_query(
        original,
        runtime=context,
        force_model=True,
        model_caller=profile,
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    assert calls == [original] and prepared.model_calls == 1
    assert prepared.original == original and prepared.rewrite == resolved
    assert prepared.decomposition == (
        "Explain validating tool-call inputs.",
        "Explain checking an HTTP response status.",
    )
    plan = compile_retrieval_plan(prepared, context)
    branches = [b for b in plan.branches if b.kind is BranchKind.HYBRID]
    assert {b.query_text for b in branches} == set(prepared.decomposition)
    assert all(b.inherit_run_id and b.inherit_reservation for b in branches)


def test_comparison_fallback_does_not_split_unresolved_or_excluded_topics() -> None:
    """Only explicit resolved comparisons receive independent retrieval topics."""
    original = "How does that differ from checking HTTP status?"
    assert resolved_comparison_parts(original, original) == ()
    assert (
        resolved_comparison_parts(
            original,
            "How does validating inputs differ from checking status without redirects?",
        )
        == ()
    )
    assert (
        resolved_comparison_parts(
            "Compare input validation and HTTP status checks.",
            "How does validating inputs differ from checking HTTP status?",
        )
        == ()
    )
