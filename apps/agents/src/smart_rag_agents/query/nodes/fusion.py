"""Fuse Hybrid ranks with resolved graph paths after correction."""

from __future__ import annotations

from smart_rag_core.query_fusion import SELECTED_FUSION_ALGORITHM, fuse_evidence
from smart_rag_core.query_fusion.assemble import fusion_input_from_branches
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.serde import branch_results_from_state

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.shared import skip_closed_nodes
from smart_rag_agents.query.state import QueryGraphState


def fuse_evidence_node(state: QueryGraphState, deps: QueryGraphDeps) -> QueryGraphState:
    """Fuse Hybrid ranks with resolved graph paths. Never graph-only answers.

    State inputs:
        ``branch_results``, ``requested_route``, ``effective_route``,
        ``keyword_extract_count``.

    State outputs:
        ``fusion``, ``selected_algorithm``, ``fusion_config_hash``,
        possibly ``effective_route=hybrid`` with a typed graph reason.

    Persistence writes:
        None. Scores are stored on graph state for citation provenance.

    External/model calls:
        None. Fusion weights are frozen constants.

    Budget/deadline behavior:
        Deadline exhaustion yields verified partial without fabricating
        relationship evidence.

    Failure/fallback route:
        Unusable graph (timeout, survival < 0.50, outage) keeps
        ``requested_route`` and sets ``effective_route=hybrid``. Hidden
        LightRAG keyword/answer counters fail closed.

    Args:
        state: State after the single correction.
        deps: Unused; fusion is pure. Present for node signature symmetry.

    Returns:
        State with a ``FusionResult`` mapping.
    """

    del deps
    if skip_closed_nodes(state):
        return state
    if state["status"] in {"refused"}:
        return state
    try:
        results = branch_results_from_state(state.get("branch_results"))
        fusion_input = fusion_input_from_branches(
            results,
            requested_route=str(state.get("requested_route") or "hybrid"),
            effective_route=str(state.get("effective_route") or "hybrid"),
        )
        fusion = fuse_evidence(fusion_input, algorithm=SELECTED_FUSION_ALGORITHM)
    except (FusionError, QueryRoutingError, ValueError) as exc:
        reason = getattr(exc, "reason", str(exc) or "fusion_failed")
        return {
            **state,
            "status": "insufficient_evidence",
            "detail": str(reason),
            "fusion": None,
        }
    return {
        **state,
        "status": "fused",
        "detail": "canonical evidence fused",
        "fusion": fusion.model_dump(mode="json"),
        "effective_route": fusion.effective_route,
        "requested_route": fusion.requested_route,
        "selected_algorithm": fusion.algorithm.value,
        "fusion_config_hash": fusion.config_hash,
        "keyword_extract_count": 0,
        "catalog_llm_call_count": 0,
    }
