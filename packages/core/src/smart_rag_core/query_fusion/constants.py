"""Frozen Combined fusion constants. These values are never model-generated.

Numeric values are duplicated from Phase 4 Hybrid quotas/RRF and Phase 5
graph survival so this module can import without loading ``retrieval``.
Tests assert they stay equal to ``RRF_K``, ``FINAL_EVIDENCE_MAX``,
``DOCUMENT_QUOTA``, ``SECTION_QUOTA``, and
``GRAPH_SURVIVAL_FALLBACK_THRESHOLD``.
"""

from __future__ import annotations

HOP_PENALTY = 0.25
"""Per extra hop in ``path_support``: ``min(edge) / (1 + 0.25 * (hops - 1))``."""

EDGE_SUPPORT_MULTIPLIER_CAP = 1.20
"""Cap on ``1 + 0.10 * (distinct_supported_edges_in_passage - 1)``."""

EDGE_SUPPORT_MULTIPLIER_STEP = 0.10
GRAPH_WEIGHT = 0.50
"""Allow-listed Combined graph branch weight. Never produced by a model."""

AGREEMENT_CAP = 1.10
"""Maximum multiplier when a passage ranks in both Hybrid and graph branches."""

GRAPH_DISCOVERED_ONLY_CAP = 0.40
"""Maximum fraction of final evidence units that are graph-discovered-only."""

FUSION_RRF_K = 60
"""RRF denominator. Must remain 60 (Phase 4 ``RRF_K``)."""

FUSION_FINAL_EVIDENCE_MAX = 12
"""Phase 4 ``FINAL_EVIDENCE_MAX``."""

FUSION_DOCUMENT_QUOTA = 2
"""Phase 4 ``DOCUMENT_QUOTA``."""

FUSION_SECTION_QUOTA = 2
"""Phase 4 ``SECTION_QUOTA``."""

FUSION_SURVIVAL_THRESHOLD = 0.50
"""Phase 5 ``GRAPH_SURVIVAL_FALLBACK_THRESHOLD``."""

FALLBACK_GRAPH_SURVIVAL_BELOW_THRESHOLD = "graph_survival_below_threshold"
FALLBACK_GRAPH_UNAVAILABLE = "graph_unavailable"
FALLBACK_GRAPH_DEADLINE = "graph_deadline"
FALLBACK_GRAPH_TIMEOUT = "graph_timeout"
FALLBACK_GRAPH_CANCELLED = "graph_cancelled"
FALLBACK_GRAPH_OUTAGE = "graph_outage"
FALLBACK_GRAPH_EMPTY = "graph_empty"
FALLBACK_HIDDEN_KEYWORD = "hidden_keyword_call"
FALLBACK_HIDDEN_LIGHTRAG_ANSWER = "hidden_lightrag_answer"
FALLBACK_MODEL_FUSION_WEIGHT = "model_fusion_weight"
FALLBACK_AGREEMENT_ABOVE_CAP = "agreement_multiplier_above_cap"
FALLBACK_NATIVE_PROSE = "native_graph_prose"
FALLBACK_BM25_SNIPPET = "bm25_snippet_evidence"
FALLBACK_UNMAPPED_PATH = "unmapped_path"
FALLBACK_MISSING_EDGE_SUPPORT = "missing_edge_support"
FALLBACK_GRAPH_ONLY_ANSWER = "graph_only_answer_forbidden"
FALLBACK_HOLDOUT_TUNING = "holdout_tuned_configuration"
FALLBACK_GLOBAL_STEERING_SCORED = "global_steering_scored"

GRAPH_DEGRADE_REASONS: frozenset[str] = frozenset(
    {
        FALLBACK_GRAPH_SURVIVAL_BELOW_THRESHOLD,
        FALLBACK_GRAPH_UNAVAILABLE,
        FALLBACK_GRAPH_DEADLINE,
        FALLBACK_GRAPH_TIMEOUT,
        FALLBACK_GRAPH_CANCELLED,
        FALLBACK_GRAPH_OUTAGE,
        FALLBACK_GRAPH_EMPTY,
        "graph_unavailable",
        "retrievers_unbound",
    }
)

USAGE_KIND_ANSWER = "answer"
USAGE_KIND_VERIFIER = "verifier"

__all__ = [
    "AGREEMENT_CAP",
    "EDGE_SUPPORT_MULTIPLIER_CAP",
    "EDGE_SUPPORT_MULTIPLIER_STEP",
    "FALLBACK_AGREEMENT_ABOVE_CAP",
    "FALLBACK_BM25_SNIPPET",
    "FALLBACK_GLOBAL_STEERING_SCORED",
    "FALLBACK_GRAPH_CANCELLED",
    "FALLBACK_GRAPH_DEADLINE",
    "FALLBACK_GRAPH_EMPTY",
    "FALLBACK_GRAPH_ONLY_ANSWER",
    "FALLBACK_GRAPH_OUTAGE",
    "FALLBACK_GRAPH_SURVIVAL_BELOW_THRESHOLD",
    "FALLBACK_GRAPH_TIMEOUT",
    "FALLBACK_GRAPH_UNAVAILABLE",
    "FALLBACK_HIDDEN_KEYWORD",
    "FALLBACK_HIDDEN_LIGHTRAG_ANSWER",
    "FALLBACK_HOLDOUT_TUNING",
    "FALLBACK_MISSING_EDGE_SUPPORT",
    "FALLBACK_MODEL_FUSION_WEIGHT",
    "FALLBACK_NATIVE_PROSE",
    "FALLBACK_UNMAPPED_PATH",
    "FUSION_DOCUMENT_QUOTA",
    "FUSION_FINAL_EVIDENCE_MAX",
    "FUSION_RRF_K",
    "FUSION_SECTION_QUOTA",
    "FUSION_SURVIVAL_THRESHOLD",
    "GRAPH_DEGRADE_REASONS",
    "GRAPH_DISCOVERED_ONLY_CAP",
    "GRAPH_WEIGHT",
    "HOP_PENALTY",
    "USAGE_KIND_ANSWER",
    "USAGE_KIND_VERIFIER",
]
