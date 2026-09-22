"""Server-owned bounds for Phase 6 packet 2 routing.

These numbers are not client-tunable. Coverage and whole-document section
thresholds stay frozen from Phase 4; this module does not retune them.
"""

from __future__ import annotations

from smart_rag_core.query_profile.versions import MAX_SUBQUESTIONS, MAX_VARIANTS
from smart_rag_core.retrieval.frozen_profile import COVERAGE_SCORE_BASELINE
from smart_rag_core.retrieval.graph import GLOBAL_STEERING_MAX

MEMORY_MESSAGE_LIMIT = 12
"""Last N authorized messages loaded when no packet-7 summary store exists."""

MEMORY_CONTENT_CHARS = 1500
"""Per-message truncation. Source documents are never copied into memory."""

BRANCH_CONCURRENCY = 2
"""Maximum independent retrieval branches running at once."""

WHOLE_DOCUMENT_SECTION_COVERAGE = 1.0
"""Whole-document summaries require exactly this ``section_coverage_ratio``."""

PROVISIONAL_COVERAGE_THRESHOLD = COVERAGE_SCORE_BASELINE
"""Frozen Phase 4 baseline. Packet 2 must not change this value."""

MAX_GRAPH_EXPANSIONS = GLOBAL_STEERING_MAX
MAX_PREP_MODEL_CALLS = 1
MAX_CORRECTIONS = 1
SUBQUESTION_CEILING = MAX_SUBQUESTIONS
VARIANT_CEILING = MAX_VARIANTS

ROUTING_SURFACE_PRODUCTION = "production"
ROUTING_SURFACE_DIAGNOSTIC = "diagnostic"

USAGE_KIND_PROFILE = "profile"
"""Rewrite plus profile share this one counted gateway kind. No second rewrite."""

FALLBACK_GRAPH_UNAVAILABLE = "graph_unavailable"
FALLBACK_ENVELOPE_CANNOT_ENLARGE = "envelope_cannot_enlarge"
FALLBACK_EMPTY_KEYWORDS = "empty_keywords"
FALLBACK_TABLE_PLAN_INCOMPLETE = "table_plan_incomplete"
FALLBACK_MEMORY_UNAVAILABLE = "memory_unavailable"
FALLBACK_RETRIEVERS_UNBOUND = "retrievers_unbound"
LIMITATION_VERIFIER_OMITTED_LINKS = "verifier_omitted_links"
LIMITATION_CITATION_LEAF_UNRESOLVED = "citation_leaf_unresolved"
"""Limitation code when one or more passage citations could not be pinned
to a single leaf and were omitted from the released answer."""

LIMITATION_VERIFIER_SKIPPED = "verifier_skipped"
"""Limitation code when the one verifier call failed or timed out and the
deterministically checked answer was released as ``verified_partial``."""

VERIFIER_SKIPPED_DETAIL_PREFIX = "verifier_skipped:"
"""Prefix for ``detail`` when the verifier was skipped. Never equal to a
``DEADLINE_REASONS`` member, so the SSE mapper does not emit ``deadline``."""

ROUTING_CORRECTION_HYBRID_TO_COMBINED = "hybrid_to_combined"
ROUTING_CORRECTION_SAME_ROUTE_RETRY = "same_route_retry"

__all__ = [
    "BRANCH_CONCURRENCY",
    "FALLBACK_EMPTY_KEYWORDS",
    "FALLBACK_ENVELOPE_CANNOT_ENLARGE",
    "FALLBACK_GRAPH_UNAVAILABLE",
    "FALLBACK_MEMORY_UNAVAILABLE",
    "FALLBACK_RETRIEVERS_UNBOUND",
    "FALLBACK_TABLE_PLAN_INCOMPLETE",
    "LIMITATION_CITATION_LEAF_UNRESOLVED",
    "LIMITATION_VERIFIER_OMITTED_LINKS",
    "LIMITATION_VERIFIER_SKIPPED",
    "MAX_CORRECTIONS",
    "MAX_GRAPH_EXPANSIONS",
    "MAX_PREP_MODEL_CALLS",
    "MEMORY_CONTENT_CHARS",
    "MEMORY_MESSAGE_LIMIT",
    "PROVISIONAL_COVERAGE_THRESHOLD",
    "ROUTING_CORRECTION_HYBRID_TO_COMBINED",
    "ROUTING_CORRECTION_SAME_ROUTE_RETRY",
    "ROUTING_SURFACE_DIAGNOSTIC",
    "ROUTING_SURFACE_PRODUCTION",
    "SUBQUESTION_CEILING",
    "USAGE_KIND_PROFILE",
    "VARIANT_CEILING",
    "VERIFIER_SKIPPED_DETAIL_PREFIX",
    "WHOLE_DOCUMENT_SECTION_COVERAGE",
]
