"""Branch-spec builders and envelope degradation helpers."""

from __future__ import annotations

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.constants import MAX_GRAPH_EXPANSIONS
from smart_rag_core.query_routing.models import (
    BranchKind,
    BranchSpec,
    QueryPreparation,
)


def hybrid_branch(
    prep: QueryPreparation,
    *,
    branch_id: str,
    query_text: str,
    group: int,
) -> BranchSpec:
    """Build one Hybrid branch inheriting packet 1 authorization.

    Args:
        prep: Typed preparation.
        branch_id: Stable id.
        query_text: Original or subquestion text.
        group: Parallel group.

    Returns:
        Hybrid ``BranchSpec``.
    """

    return BranchSpec(
        branch_id=branch_id,
        kind=BranchKind.HYBRID,
        family=Phase6RouteFamily.HYBRID,
        query_text=query_text,
        parallel_group=group,
        hl_keywords=prep.hl_keywords,
        ll_keywords=prep.ll_keywords,
    )


def graph_branch(
    prep: QueryPreparation,
    *,
    branch_id: str,
    kind: BranchKind,
    family: Phase6RouteFamily,
    group: int,
) -> BranchSpec:
    """Build one graph lead branch with precomputed keywords only.

    Args:
        prep: Typed preparation.
        branch_id: Stable id.
        kind: Local, hybrid, or global steering.
        family: Combined or inspection.
        group: Parallel group.

    Returns:
        Graph ``BranchSpec``. Empty keywords are left for execute to fail closed.
    """

    return BranchSpec(
        branch_id=branch_id,
        kind=kind,
        family=family,
        query_text=prep.original,
        parallel_group=group,
        hl_keywords=prep.hl_keywords,
        ll_keywords=prep.ll_keywords,
        max_graph_expansions=MAX_GRAPH_EXPANSIONS,
    )


def citation_branch(prep: QueryPreparation, *, group: int) -> BranchSpec:
    """Build ID-resolution-only citation lookup.

    Args:
        prep: Typed preparation.
        group: Parallel group.

    Returns:
        Citation lookup spec. Not a catalog tool.
    """

    return BranchSpec(
        branch_id="cite-0",
        kind=BranchKind.CITATION_LOOKUP,
        family=Phase6RouteFamily.HYBRID,
        query_text=prep.original,
        parallel_group=group,
        hl_keywords=prep.hl_keywords,
        ll_keywords=prep.ll_keywords,
    )


def degrade_branches_to_hybrid(
    prep: QueryPreparation,
    branches: tuple[BranchSpec, ...],
) -> tuple[BranchSpec, ...]:
    """Drop graph branches when the reserved envelope cannot enlarge.

    Args:
        prep: Typed preparation.
        branches: Planned branches.

    Returns:
        Hybrid/table/refusal branches only.
    """

    kept: list[BranchSpec] = []
    for branch in branches:
        if branch.kind in {
            BranchKind.GRAPH_LOCAL,
            BranchKind.GRAPH_HYBRID,
            BranchKind.GRAPH_GLOBAL_STEERING,
        }:
            continue
        kept.append(branch)
    if not any(item.kind is BranchKind.HYBRID for item in kept):
        kept.insert(
            0,
            hybrid_branch(prep, branch_id="hyb-0", query_text=prep.original, group=0),
        )
    return tuple(kept)
