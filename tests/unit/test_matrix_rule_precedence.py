"""Isolated named-rule tests for the deterministic route matrix."""

from __future__ import annotations

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.coverage_policy import query_type_for
from smart_rag_core.query_routing.matrix_rules import (
    MATRIX_RULES,
    MatrixContext,
    apply_matrix_rules,
)
from smart_rag_core.query_routing.preparation import prepare_query

from tests.support.query_runtime import authorized_runtime as _runtime


def _context(
    query: str, *, section_coverage_ratio: float | None = None
) -> MatrixContext:
    """Build a matrix context for one deterministic preparation.

    Args:
        query: Original user text.
        section_coverage_ratio: Optional whole-document ratio.

    Returns:
        Mutable matrix context with default flags.
    """

    runtime = _runtime()
    prep = prepare_query(query, runtime=runtime)
    return MatrixContext(
        prep=prep,
        extract_query_type=query_type_for(prep),
        mapped_family=Phase6RouteFamily.HYBRID,
        mapped_limitation=None,
        section_coverage_ratio=section_coverage_ratio,
        flags={
            "company_claim_forbidden": False,
            "graph_as_answer_forbidden": False,
            "media_answer_forbidden": False,
            "hybrid_prose_composition": False,
            "relationship_signal_retained": prep.low_confidence_relationship
            or prep.relationship_intent,
        },
    )


def test_matrix_rule_names_preserve_documented_precedence() -> None:
    """The immutable rule tuple order is the accepted precedence."""

    assert tuple(name for name, _rule in MATRIX_RULES) == (
        "web_research",
        "no_retrieval",
        "graph_inspection",
        "unsupported_media",
        "negation",
        "historical_relationship",
        "whole_document_summary",
        "global_steering",
        "comparison_or_multipart",
        "structured_table",
        "current_relationship",
        "low_confidence_relationship",
        "ordinary_hybrid",
    )


def test_named_rules_win_in_isolation() -> None:
    """Each representative query selects the expected named rule."""

    cases = (
        ("search the web for latest news", "web_research"),
        ("Hello", "no_retrieval"),
        ("Inspect the current graph workspace", "graph_inspection"),
        ("Describe the unlabeled chart in the figure", "unsupported_media"),
        ("What is not allowed for INV-SR-1001?", "negation"),
        (
            "Which team owns the widget after the handoff as of 2020-01-01?",
            "historical_relationship",
        ),
        ("Summarize document p4-src-0001", "whole_document_summary"),
        (
            "What is the corpus-wide landscape of safety themes?",
            "global_steering",
        ),
        (
            "Compare INV-SR-1001 policy and sum the Q1 sheet",
            "comparison_or_multipart",
        ),
        ("sum the Q1 sheet totals", "structured_table"),
        (
            "Which team owns INV-SR-1001 related to procurement?",
            "current_relationship",
        ),
        ("What is the status of INV-SR-1001?", "ordinary_hybrid"),
    )
    for query, expected in cases:
        name, _decision = apply_matrix_rules(_context(query))
        assert name == expected, query
    name, decision = apply_matrix_rules(
        _context("Summarize document p4-src-0001", section_coverage_ratio=0.5)
    )
    assert name == "whole_document_summary"
    assert decision.family is Phase6RouteFamily.SCOPED_REFUSAL
