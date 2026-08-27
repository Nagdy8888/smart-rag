"""Immutable route-matrix cases with descriptive IDs for failed-case lookup."""

from __future__ import annotations

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.models import BranchKind

from tests.support.query_routing import NO_LIMITATIONS

MATRIX_ROUTE_CASES: tuple[
    tuple[str, str, Phase6RouteFamily, set[BranchKind], set[str]],
    ...,
] = (
    (
        "hybrid-invoice-status",
        "What is the status of INV-SR-1001?",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        NO_LIMITATIONS,
    ),
    (
        "hybrid-orion-alias-policy",
        "Define the Orion widget alias policy date.",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        NO_LIMITATIONS,
    ),
    (
        "combined-invoice-team-ownership",
        "Which team owns INV-SR-1001 related to procurement?",
        Phase6RouteFamily.COMBINED,
        {BranchKind.HYBRID, BranchKind.GRAPH_LOCAL},
        NO_LIMITATIONS,
    ),
    (
        "hybrid-historical-handoff-2020",
        "Which team owns the widget after the handoff as of 2020-01-01?",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        {"temporal_graph_limitation"},
    ),
    (
        "hybrid-ordinary-safety-themes",
        "Summarize ordinary safety themes.",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        NO_LIMITATIONS,
    ),
    (
        "combined-corpus-safety-landscape",
        "What is the corpus-wide landscape of safety themes?",
        Phase6RouteFamily.COMBINED,
        {BranchKind.HYBRID, BranchKind.GRAPH_GLOBAL_STEERING},
        {"global_steering_only"},
    ),
    (
        "hybrid-whole-document-p4-src-0001",
        "Summarize document p4-src-0001",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        {"whole_document_section_coverage"},
    ),
    (
        "hybrid-negation-invoice-not-allowed",
        "What is not allowed for INV-SR-1001?",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        {"negation_unscoped"},
    ),
    (
        "refusal-unlabeled-chart",
        "Describe the unlabeled chart in the figure",
        Phase6RouteFamily.SCOPED_REFUSAL,
        {BranchKind.SCOPED_REFUSAL},
        {"media_limitation"},
    ),
    (
        "hybrid-prj-alpha-leave-compare",
        "Compare PRJ-ALPHA leave days and notice period.",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        NO_LIMITATIONS,
    ),
    (
        "composite-invoice-policy-and-q1",
        "Compare INV-SR-1001 policy and sum the Q1 sheet",
        Phase6RouteFamily.COMPOSITE,
        {BranchKind.HYBRID, BranchKind.STRUCTURED_TABLE},
        NO_LIMITATIONS,
    ),
    (
        "table-q1-sheet-totals",
        "sum the Q1 sheet totals",
        Phase6RouteFamily.STRUCTURED_TABLE,
        {BranchKind.STRUCTURED_TABLE},
        NO_LIMITATIONS,
    ),
    (
        "inspection-current-graph-workspace",
        "Inspect the current graph workspace",
        Phase6RouteFamily.GRAPH_INSPECTION,
        {BranchKind.GRAPH_INSPECTION},
        {"graph_inspection_only"},
    ),
    (
        "no-retrieval-hello",
        "Hello",
        Phase6RouteFamily.NO_RETRIEVAL,
        {BranchKind.NO_RETRIEVAL},
        {"no_retrieval"},
    ),
    (
        "no-retrieval-rewrite-without-files",
        "Rewrite this paragraph without company files",
        Phase6RouteFamily.NO_RETRIEVAL,
        {BranchKind.NO_RETRIEVAL},
        {"no_retrieval"},
    ),
    (
        "hybrid-low-confidence-invoice",
        "maybe related to INV-SR-1001",
        Phase6RouteFamily.HYBRID,
        {BranchKind.HYBRID},
        {"low_confidence_relationship"},
    ),
)
