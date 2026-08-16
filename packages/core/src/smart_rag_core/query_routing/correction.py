"""One global routing/retrieval correction. Never both kinds and never a loop."""

from __future__ import annotations

from smart_rag_core.query_admission.ceilings import assert_correction_available
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.constants import (
    PROVISIONAL_COVERAGE_THRESHOLD,
    ROUTING_CORRECTION_HYBRID_TO_COMBINED,
    ROUTING_CORRECTION_SAME_ROUTE_RETRY,
)
from smart_rag_core.query_routing.envelope import family_fits_reservation
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchResult,
    BranchSpec,
    CorrectionDecision,
    CorrectionKind,
    QueryPreparation,
    RetrievalPlan,
)
from smart_rag_core.retrieval.frozen_profile import coverage_threshold_for


def decide_correction(
    plan: RetrievalPlan,
    prep: QueryPreparation,
    branch_results: tuple[BranchResult, ...],
    *,
    runtime: AuthorizedRuntimeContext,
    remaining_corrections: int,
    already_applied: bool,
    coverage_threshold_override: float | None = None,
) -> CorrectionDecision:
    """Spend at most one correction: Hybrid→Combined or same-route retry.

    Args:
        plan: Compiled retrieval plan.
        prep: Typed preparation.
        branch_results: Branch outcomes including Hybrid coverage.
        runtime: Packet 1 context used to refuse envelope enlargement.
        remaining_corrections: Remaining correction slots from graph state.
        already_applied: True when this run already spent the correction.
        coverage_threshold_override: Forbidden unless it equals the freeze.

    Returns:
        Correction decision. Exhaustion sets ``insufficient_evidence``.

    Raises:
        QueryRoutingError: Second correction, correction loop, or holdout
            threshold change.
    """

    if already_applied:
        raise QueryRoutingError("correction_loop")
    frozen = coverage_threshold_for(None)
    if abs(frozen - PROVISIONAL_COVERAGE_THRESHOLD) > 1e-12:
        raise QueryRoutingError("holdout_driven_threshold_change")
    if coverage_threshold_override is not None and (
        abs(coverage_threshold_override - plan.coverage_threshold) > 1e-12
        or abs(coverage_threshold_override - frozen) > 1e-12
    ):
        raise QueryRoutingError("holdout_driven_threshold_change")
    threshold = plan.coverage_threshold
    if remaining_corrections <= 0:
        return CorrectionDecision(
            applied=False,
            kind=CorrectionKind.NONE,
            reason="correction_exhausted",
            remaining_corrections=0,
            exhausted_status=_weak_status(branch_results, threshold),
            already_applied=False,
        )
    hybrid = _hybrid_result(branch_results)
    coverage = hybrid.coverage_score if hybrid is not None else None
    if coverage is None or coverage >= threshold:
        return CorrectionDecision(
            applied=False,
            kind=CorrectionKind.NONE,
            reason="coverage_meets_threshold",
            remaining_corrections=remaining_corrections,
            already_applied=False,
        )
    retained = (
        plan.relationship_signal_retained
        and not plan.historical_relationship
        and not plan.temporal_graph_limitation
    )
    if retained and family_fits_reservation(
        Phase6RouteFamily.COMBINED, runtime.route_family
    ):
        try:
            remaining = assert_correction_available(remaining_corrections)
        except QueryCeilingError as exc:
            raise QueryRoutingError("second_correction") from exc
        return CorrectionDecision(
            applied=True,
            kind=CorrectionKind.HYBRID_TO_COMBINED,
            reason="coverage_below_threshold_with_relationship",
            routing_correction=ROUTING_CORRECTION_HYBRID_TO_COMBINED,
            remaining_corrections=remaining,
            already_applied=True,
        )
    if not retained:
        try:
            remaining = assert_correction_available(remaining_corrections)
        except QueryCeilingError as exc:
            raise QueryRoutingError("second_correction") from exc
        return CorrectionDecision(
            applied=True,
            kind=CorrectionKind.SAME_ROUTE_RETRY,
            reason="coverage_below_threshold_same_route",
            routing_correction=ROUTING_CORRECTION_SAME_ROUTE_RETRY,
            remaining_corrections=remaining,
            already_applied=True,
        )
    return CorrectionDecision(
        applied=False,
        kind=CorrectionKind.NONE,
        reason="escalation_envelope_blocked",
        remaining_corrections=remaining_corrections,
        exhausted_status="insufficient_evidence",
        already_applied=False,
    )


def apply_correction_to_plan(
    plan: RetrievalPlan,
    prep: QueryPreparation,
    decision: CorrectionDecision,
    branch_results: tuple[BranchResult, ...],
) -> RetrievalPlan:
    """Return a plan with at most one extra Combined or retry branch.

    Args:
        plan: Original plan.
        prep: Typed preparation.
        decision: Single correction decision.
        branch_results: Prior branch outcomes for Hybrid candidate reuse.

    Returns:
        Updated plan. Combined fusion is not performed here.

    Raises:
        QueryRoutingError: Historical graph path or second correction kind.
    """

    if not decision.applied:
        return plan
    if decision.kind is CorrectionKind.HYBRID_TO_COMBINED:
        if plan.historical_relationship or plan.temporal_graph_limitation:
            raise QueryRoutingError("historical_graph_path")
        hybrid = _hybrid_result(branch_results)
        reused = hybrid.ranked_ids if hybrid is not None else ()
        extra = BranchSpec(
            branch_id="corr-combined",
            kind=BranchKind.GRAPH_HYBRID,
            family=Phase6RouteFamily.COMBINED,
            query_text=prep.rewrite or prep.original,
            parallel_group=0,
            hl_keywords=prep.hl_keywords,
            ll_keywords=prep.ll_keywords,
            reuse_hybrid_ranked_ids=reused,
        )
        return plan.model_copy(
            update={
                "corrected_route": Phase6RouteFamily.COMBINED,
                "effective_route": Phase6RouteFamily.COMBINED,
                "branches": (*plan.branches, extra),
                "relationship_signal_retained": True,
            }
        )
    if decision.kind is CorrectionKind.SAME_ROUTE_RETRY:
        extra = BranchSpec(
            branch_id="corr-retry",
            kind=BranchKind.HYBRID,
            family=plan.effective_route
            if plan.effective_route is not Phase6RouteFamily.COMBINED
            else Phase6RouteFamily.HYBRID,
            query_text=prep.rewrite or prep.original,
            parallel_group=0,
            hl_keywords=prep.hl_keywords,
            ll_keywords=prep.ll_keywords,
        )
        return plan.model_copy(
            update={
                "corrected_route": plan.effective_route,
                "branches": (*plan.branches, extra),
            }
        )
    raise QueryRoutingError("second_correction")


def refuse_second_correction(already_applied: bool) -> None:
    """Fail closed when a second correction is requested.

    Args:
        already_applied: Whether the single budget was already spent.

    Raises:
        QueryRoutingError: ``second_correction``.
    """

    if already_applied:
        raise QueryRoutingError("second_correction")


def _hybrid_result(results: tuple[BranchResult, ...]) -> BranchResult | None:
    """Return the first Hybrid branch result.

    Args:
        results: Branch outcomes.

    Returns:
        Hybrid result or None.
    """

    for item in results:
        if item.kind is BranchKind.HYBRID:
            return item
    return None


def _weak_status(
    results: tuple[BranchResult, ...],
    threshold: float,
) -> str | None:
    """Return insufficient-evidence when Hybrid coverage is still weak.

    Args:
        results: Branch outcomes.
        threshold: Frozen coverage threshold.

    Returns:
        ``insufficient_evidence`` or None.
    """

    hybrid = _hybrid_result(results)
    if hybrid is None:
        return None
    if hybrid.coverage_score is not None and hybrid.coverage_score < threshold:
        return "insufficient_evidence"
    return None
