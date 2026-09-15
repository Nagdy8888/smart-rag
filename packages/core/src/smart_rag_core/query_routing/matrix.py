"""Thin compiler over the ordered named route/limitation matrix."""

from __future__ import annotations

from smart_rag_core.evaluation.schema import QueryType
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import (
    Phase6RouteFamily,
    map_query_type_to_phase6_family,
)
from smart_rag_core.query_routing.branch_specs import degrade_branches_to_hybrid
from smart_rag_core.query_routing.constants import (
    BRANCH_CONCURRENCY,
    SUBQUESTION_CEILING,
    WHOLE_DOCUMENT_SECTION_COVERAGE,
)
from smart_rag_core.query_routing.coverage_policy import (
    evaluation_class_for,
    frozen_coverage_threshold,
    query_type_for,
)
from smart_rag_core.query_routing.envelope import (
    clamp_family_to_reservation,
    reject_production_manual_override,
)
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.knowledge_scope import no_retrieval_mode_for_scope
from smart_rag_core.query_routing.matrix_rules import MatrixContext, apply_matrix_rules
from smart_rag_core.query_routing.models import (
    BranchKind,
    QueryPreparation,
    RetrievalPlan,
    RoutingSurface,
)

__all__ = [
    "compile_retrieval_plan",
    "evaluation_class_for",
    "frozen_coverage_threshold",
]


def compile_retrieval_plan(
    prep: QueryPreparation,
    runtime: AuthorizedRuntimeContext,
    *,
    requested_manual_route: str | None = None,
    section_coverage_ratio: float | None = None,
) -> RetrievalPlan:
    """Compile the allow-listed route/limitation matrix.

    Core routes are deterministic. Catalog-search LLMs are never consulted.
    Production manual routing is rejected. The planner never exceeds the
    packet 1 reserved envelope.

    Args:
        prep: Typed preparation. Original query is required.
        runtime: Packet 1 authorized runtime. ``route_family`` is the envelope.
        requested_manual_route: Diagnostic-only override.
        section_coverage_ratio: Known whole-document ratio when already scored.

    Returns:
        Frozen retrieval plan with bounded branches.

    Raises:
        QueryRoutingError: Production manual override, fourth subquestion,
            unproved complement, graph-only answer, NoRetrieval claim, or
            ``web_envelope_cannot_fit``.
    """

    reject_production_manual_override(
        surface=prep.routing_surface.value,
        requested_manual_route=requested_manual_route,
    )
    extract_query_type = query_type_for(prep)
    query_class = evaluation_class_for(prep)
    mapped = map_query_type_to_phase6_family(
        extract_query_type,
        query_class,
        historical_relationship=prep.historical_relationship,
        comparison=prep.comparison and extract_query_type is QueryType.MULTI_PART,
        scoped_summary_incomplete=(
            prep.whole_document_summary
            and section_coverage_ratio is not None
            and section_coverage_ratio < WHOLE_DOCUMENT_SECTION_COVERAGE
        ),
    )
    threshold = frozen_coverage_threshold(prep)
    surface = prep.routing_surface
    manual = prep.manual_mode
    flags = {
        "company_claim_forbidden": False,
        "graph_as_answer_forbidden": False,
        "media_answer_forbidden": False,
        "hybrid_prose_composition": False,
        "relationship_signal_retained": prep.low_confidence_relationship
        or prep.relationship_intent,
    }
    _name, decision = apply_matrix_rules(
        MatrixContext(
            prep=prep,
            extract_query_type=extract_query_type,
            mapped_family=mapped.phase6_family,
            mapped_limitation=mapped.limitation,
            section_coverage_ratio=section_coverage_ratio,
            flags=flags,
        )
    )
    del _name
    desired = decision.family
    limitations = decision.limitations
    branches = decision.branches
    if surface is RoutingSurface.DIAGNOSTIC and requested_manual_route and manual:
        try:
            desired = Phase6RouteFamily(requested_manual_route)
        except ValueError as exc:
            raise QueryRoutingError("unknown_manual_route") from exc
    effective, envelope_reason = clamp_family_to_reservation(desired, runtime)
    if envelope_reason:
        limitations = (*limitations, envelope_reason)
        branches = degrade_branches_to_hybrid(prep, branches)
        flags["relationship_signal_retained"] = bool(
            flags.get("relationship_signal_retained") or prep.relationship_intent
        )
    if effective is Phase6RouteFamily.COMPOSITE:
        families = {
            branch.family
            for branch in branches
            if branch.kind
            not in {
                BranchKind.CITATION_LOOKUP,
                BranchKind.NO_RETRIEVAL,
                BranchKind.SCOPED_REFUSAL,
            }
        }
        if len(families) <= 1:
            effective = next(iter(families), Phase6RouteFamily.HYBRID)
    return RetrievalPlan(
        requested_route=runtime.route_family,
        effective_route=effective,
        corrected_route=None,
        branches=branches,
        limitations=tuple(dict.fromkeys(limitations)),
        historical_relationship=prep.historical_relationship,
        temporal_graph_limitation="temporal_graph_limitation" in limitations,
        whole_document_summary=prep.whole_document_summary,
        section_coverage_required=WHOLE_DOCUMENT_SECTION_COVERAGE,
        coverage_threshold=threshold,
        company_claim_forbidden=flags["company_claim_forbidden"],
        graph_as_answer_forbidden=flags["graph_as_answer_forbidden"],
        prove_complement=False,
        media_answer_forbidden=flags["media_answer_forbidden"],
        manual_mode=manual,
        routing_surface=surface,
        hybrid_prose_composition=flags["hybrid_prose_composition"],
        relationship_signal_retained=flags["relationship_signal_retained"],
        fallback_reason=envelope_reason,
        branch_concurrency=BRANCH_CONCURRENCY,
        max_subquestions=SUBQUESTION_CEILING,
        catalog_llm_call_count=0,
        knowledge_scope=prep.knowledge_scope,
        no_retrieval_answer_mode=no_retrieval_mode_for_scope(prep.knowledge_scope),
        scope_degradation_reason=prep.scope_degradation_reason,
        requested_search_scope=prep.requested_search_scope,
    )
