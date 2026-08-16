"""Byte-identical Combined fusion formulas. Weights are never model-generated."""

from __future__ import annotations

from smart_rag_core.query_fusion.constants import (
    AGREEMENT_CAP,
    EDGE_SUPPORT_MULTIPLIER_CAP,
    EDGE_SUPPORT_MULTIPLIER_STEP,
    FALLBACK_AGREEMENT_ABOVE_CAP,
    FALLBACK_MODEL_FUSION_WEIGHT,
    FUSION_RRF_K,
    GRAPH_WEIGHT,
    HOP_PENALTY,
)
from smart_rag_core.query_fusion.exceptions import FusionError


def path_support(*, min_edge_support: float, hop_count: int) -> float:
    """Return path support after the frozen hop penalty.

    ``path_support = min(edge_support_confidence) / (1 + 0.25 * (hop_count - 1))``.

    Args:
        min_edge_support: Minimum surviving edge support on the path.
        hop_count: Statement count, at least 1 and at most 3.

    Returns:
        Path support in ``(0, 1]`` for typical mapping supports.

    Raises:
        FusionError: If ``hop_count`` is outside ``[1, 3]``.
    """

    if hop_count < 1 or hop_count > 3:
        raise FusionError("hop_count_out_of_bounds")
    return min_edge_support / (1.0 + HOP_PENALTY * (hop_count - 1))


def edge_support_multiplier(distinct_supported_edges_in_passage: int) -> float:
    """Return the per-passage edge-support multiplier, capped at 1.20.

    ``min(1.20, 1 + 0.10 * (distinct_supported_edges_in_passage - 1))``.

    Args:
        distinct_supported_edges_in_passage: Distinct path edges this passage
            supports. Must be at least 1 for a contributing path.

    Returns:
        Multiplier in ``[1.0, 1.20]``.

    Raises:
        FusionError: If the distinct-edge count is less than 1.
    """

    if distinct_supported_edges_in_passage < 1:
        raise FusionError("no_supported_edges_in_passage")
    raw = 1.0 + EDGE_SUPPORT_MULTIPLIER_STEP * (distinct_supported_edges_in_passage - 1)
    return min(EDGE_SUPPORT_MULTIPLIER_CAP, raw)


def graph_passage_strength_for_path(
    *,
    min_edge_support: float,
    hop_count: int,
    distinct_supported_edges_in_passage: int,
) -> float:
    """Return one path's contribution to ``graph_passage_strength``.

    Args:
        min_edge_support: Minimum edge support on the path.
        hop_count: Path hop count.
        distinct_supported_edges_in_passage: Edges of this path the passage
            supports.

    Returns:
        ``path_support * edge_support_multiplier``.
    """

    return path_support(
        min_edge_support=min_edge_support, hop_count=hop_count
    ) * edge_support_multiplier(distinct_supported_edges_in_passage)


def combined_rrf_score(
    *,
    hybrid_rank: int | None,
    graph_rank: int | None,
    graph_weight: float = GRAPH_WEIGHT,
) -> float:
    """Return Combined RRF with frozen k=60 and graph weight 0.50.

    ``combined_score = 1.00/(60 + hybrid_rank) + 0.50/(60 + graph_rank)``.
    An absent branch contributes zero.

    Args:
        hybrid_rank: 1-based post-rerank (or allowed RRF fallback) rank.
        graph_rank: 1-based rank by ``graph_passage_strength``.
        graph_weight: Must equal the frozen ``0.50``. Callers cannot pass a
            model-produced weight.

    Returns:
        Combined score. Zero when both branches are absent.

    Raises:
        FusionError: If ``graph_weight`` is not the frozen constant.
    """

    assert_constant_graph_weight(graph_weight)
    hybrid_term = 0.0 if hybrid_rank is None else 1.00 / (FUSION_RRF_K + hybrid_rank)
    graph_term = (
        0.0 if graph_rank is None else graph_weight / (FUSION_RRF_K + graph_rank)
    )
    return hybrid_term + graph_term


def apply_agreement_multiplier(
    score: float,
    *,
    ranks_in_both: bool,
    multiplier: float = AGREEMENT_CAP,
) -> float:
    """Apply at most a 1.10 agreement multiplier when both branches rank.

    Args:
        score: Combined RRF score before agreement.
        ranks_in_both: True when the passage has both ``hybrid_rank`` and
            ``graph_rank``.
        multiplier: Requested multiplier. Values above ``1.10`` fail closed.

    Returns:
        ``score`` unchanged, or ``score * min(multiplier, 1.10)`` when both
        branches ranked the passage.

    Raises:
        FusionError: If ``multiplier`` exceeds the frozen cap.
    """

    if multiplier > AGREEMENT_CAP + 1e-12:
        raise FusionError(FALLBACK_AGREEMENT_ABOVE_CAP)
    if not ranks_in_both:
        return score
    return score * min(multiplier, AGREEMENT_CAP)


def assert_constant_graph_weight(weight: float) -> None:
    """Reject an LLM-generated or otherwise non-frozen graph weight.

    Args:
        weight: Candidate graph branch weight.

    Raises:
        FusionError: ``model_fusion_weight`` when ``weight`` is not ``0.50``.
    """

    if abs(weight - GRAPH_WEIGHT) > 1e-12:
        raise FusionError(FALLBACK_MODEL_FUSION_WEIGHT)
