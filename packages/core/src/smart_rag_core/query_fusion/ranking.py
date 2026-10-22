"""Resolved-path Combined ranking using the frozen hop-penalty RRF formulas."""

from __future__ import annotations

from collections import defaultdict

from smart_rag_core.query_fusion.constants import (
    FALLBACK_BM25_SNIPPET,
    FALLBACK_GLOBAL_STEERING_SCORED,
    FALLBACK_MISSING_EDGE_SUPPORT,
    FALLBACK_NATIVE_PROSE,
    FALLBACK_UNMAPPED_PATH,
    FUSION_SURVIVAL_THRESHOLD,
    GRAPH_DEGRADE_REASONS,
    GRAPH_WEIGHT,
)
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.formulas import (
    apply_agreement_multiplier,
    combined_rrf_score,
    graph_passage_strength_for_path,
)
from smart_rag_core.query_fusion.formulas import (
    path_support as path_support_score,
)
from smart_rag_core.query_fusion.models import (
    FusionInput,
    GraphPassage,
    GraphPathInput,
    HybridPassage,
    PassageOrigin,
    ScoredPassage,
)


def discard_unusable_paths(
    paths: tuple[GraphPathInput, ...],
    *,
    steering_chunk_ids: frozenset[str],
) -> tuple[tuple[GraphPathInput, ...], tuple[str, ...]]:
    """Keep only fully mapped authorized current paths with edge support.

    Args:
        paths: Candidate application paths.
        steering_chunk_ids: GlobalSteering expansions. Never graph-scored.

    Returns:
        Surviving paths and machine-readable discard reasons.

    Raises:
        FusionError: If a path is marked steering-only yet still fully mapped
            for scoring, or native prose is presented as evidence.
    """

    kept: list[GraphPathInput] = []
    reasons: list[str] = []
    for path in paths:
        if path.steering_only:
            reasons.append(FALLBACK_GLOBAL_STEERING_SCORED)
            continue
        if path.native_prose:
            raise FusionError(FALLBACK_NATIVE_PROSE)
        if path.unmapped or not path.fully_mapped:
            reasons.append(FALLBACK_UNMAPPED_PATH)
            continue
        if path.missing_edge_support or not path.edge_supports:
            reasons.append(FALLBACK_MISSING_EDGE_SUPPORT)
            continue
        if path.stale or path.deleted or path.unauthorized:
            reasons.append(FALLBACK_UNMAPPED_PATH)
            continue
        if any(chunk_id in steering_chunk_ids for chunk_id in path.canonical_chunk_ids):
            reasons.append(FALLBACK_GLOBAL_STEERING_SCORED)
            continue
        kept.append(path)
    return tuple(kept), tuple(reasons)


def graph_strengths(
    paths: tuple[GraphPathInput, ...],
) -> dict[str, tuple[float, float, tuple[str, ...]]]:
    """Return per-chunk max graph_passage_strength, path_support, and statements.

    Args:
        paths: Fully mapped surviving paths.

    Returns:
        Mapping of chunk_id to ``(strength, path_support, statement_ids)``.
    """

    best: dict[str, tuple[float, float, tuple[str, ...]]] = {}
    for path in paths:
        support = path_support_score(
            min_edge_support=min(path.edge_supports),
            hop_count=path.hops,
        )
        per_chunk_edges: dict[str, set[int]] = defaultdict(set)
        if path.edge_chunk_ids:
            for index, chunk_ids in enumerate(path.edge_chunk_ids):
                for chunk_id in chunk_ids:
                    per_chunk_edges[chunk_id].add(index)
        else:
            for chunk_id in path.canonical_chunk_ids:
                for index in range(path.hops):
                    per_chunk_edges[chunk_id].add(index)
        for chunk_id, edges in per_chunk_edges.items():
            strength = graph_passage_strength_for_path(
                min_edge_support=min(path.edge_supports),
                hop_count=path.hops,
                distinct_supported_edges_in_passage=len(edges),
            )
            previous = best.get(chunk_id)
            if previous is None or strength > previous[0]:
                best[chunk_id] = (strength, support, path.statement_ids)
    return best


def graph_ranks(
    strengths: dict[str, tuple[float, float, tuple[str, ...]]],
) -> dict[str, int]:
    """Rank canonical passages by graph_passage_strength, 1-based.

    Ties break by chunk_id ascending.

    Args:
        strengths: Per-chunk strength tuples.

    Returns:
        Mapping of chunk_id to graph_rank.
    """

    ordered = sorted(
        strengths.items(),
        key=lambda item: (-item[1][0], item[0]),
    )
    return {
        chunk_id: index for index, (chunk_id, _payload) in enumerate(ordered, start=1)
    }


def usable_hybrid_passages(
    passages: tuple[HybridPassage, ...],
) -> tuple[HybridPassage, ...]:
    """Drop deleted, unauthorized, or BM25-snippet Hybrid units.

    Args:
        passages: Hybrid evidence snapshots.

    Returns:
        Authorized current Hybrid passages.

    Raises:
        FusionError: If a BM25 snippet is marked as evidence.
    """

    kept: list[HybridPassage] = []
    for item in passages:
        if item.bm25_snippet:
            raise FusionError(FALLBACK_BM25_SNIPPET)
        if item.deleted or item.unauthorized or not item.authorized_current:
            continue
        kept.append(item)
    return tuple(kept)


def usable_graph_passages(
    passages: tuple[GraphPassage, ...],
) -> dict[str, GraphPassage]:
    """Index authorized current graph locators. Native prose fails closed.

    Args:
        passages: Graph-resolved canonical locators.

    Returns:
        Mapping of chunk_id to locator.

    Raises:
        FusionError: If native graph prose is supplied as citation text.
    """

    indexed: dict[str, GraphPassage] = {}
    for item in passages:
        if item.native_prose:
            raise FusionError(FALLBACK_NATIVE_PROSE)
        if item.deleted or item.unauthorized or not item.authorized_current:
            continue
        indexed[item.chunk_id] = item
    return indexed


def score_resolved_path_fusion(
    fusion_input: FusionInput,
    *,
    graph_usable: bool,
) -> tuple[tuple[ScoredPassage, ...], tuple[str, ...]]:
    """Score canonical passages with resolved-path fusion.

    Args:
        fusion_input: Hybrid ranks plus resolved graph paths.
        graph_usable: False when Combined degrades to Hybrid.

    Returns:
        Unbounded scored passages (quotas applied by the caller) and path
        discard reasons.

    Raises:
        FusionError: Native prose, BM25 snippets, or graph-only answer.
    """

    hybrid = usable_hybrid_passages(fusion_input.hybrid_passages)
    locators = usable_graph_passages(fusion_input.graph_passages)
    steering = frozenset(fusion_input.global_steering_chunk_ids)
    discarded: tuple[str, ...] = ()
    strengths: dict[str, tuple[float, float, tuple[str, ...]]] = {}
    ranks: dict[str, int] = {}
    if graph_usable:
        kept_paths, discarded = discard_unusable_paths(
            fusion_input.graph_paths,
            steering_chunk_ids=steering,
        )
        strengths = graph_strengths(kept_paths)
        ranks = graph_ranks(strengths)
        for chunk_id in steering:
            if chunk_id in ranks:
                raise FusionError(FALLBACK_GLOBAL_STEERING_SCORED)
    hybrid_by_id = {item.chunk_id: item for item in hybrid}
    chunk_ids = list(dict.fromkeys((*hybrid_by_id, *ranks)))
    scored: list[ScoredPassage] = []
    for chunk_id in chunk_ids:
        hybrid_item = hybrid_by_id.get(chunk_id)
        locator = locators.get(chunk_id)
        hybrid_rank = hybrid_item.hybrid_rank if hybrid_item is not None else None
        graph_rank = ranks.get(chunk_id)
        strength_tuple = strengths.get(chunk_id)
        origin = PassageOrigin.HYBRID
        if hybrid_rank is not None and graph_rank is not None:
            origin = PassageOrigin.BOTH
        elif graph_rank is not None:
            origin = PassageOrigin.GRAPH_RESOLVED
        score = combined_rrf_score(
            hybrid_rank=hybrid_rank,
            graph_rank=graph_rank,
            graph_weight=GRAPH_WEIGHT,
        )
        score = apply_agreement_multiplier(
            score,
            ranks_in_both=hybrid_rank is not None and graph_rank is not None,
        )
        citation = hybrid_item.citation_text if hybrid_item is not None else ""
        if not citation and locator is not None:
            citation = locator.citation_text
        document_id = (
            hybrid_item.document_id
            if hybrid_item is not None
            else locator.document_id
            if locator is not None
            else chunk_id
        )
        version_id = (
            hybrid_item.version_id
            if hybrid_item is not None
            else locator.version_id
            if locator is not None
            else chunk_id
        )
        section = (
            hybrid_item.section_path
            if hybrid_item is not None
            else locator.section_path
            if locator is not None
            else ()
        )
        scored.append(
            ScoredPassage(
                chunk_id=chunk_id,
                document_id=document_id,
                version_id=version_id,
                citation_text=citation,
                parent_chunk_id=hybrid_item.parent_chunk_id if hybrid_item else None,
                hybrid_rank=hybrid_rank,
                graph_rank=graph_rank,
                graph_passage_strength=(
                    strength_tuple[0] if strength_tuple is not None else None
                ),
                path_support=strength_tuple[1] if strength_tuple is not None else None,
                combined_score=score,
                origin=origin,
                graph_discovered_only=hybrid_rank is None and graph_rank is not None,
                section_path=section,
                page_number=(
                    hybrid_item.page_number
                    if hybrid_item is not None
                    else locator.page_number
                    if locator is not None
                    else None
                ),
                sheet_name=(
                    hybrid_item.sheet_name
                    if hybrid_item is not None
                    else locator.sheet_name
                    if locator is not None
                    else None
                ),
                range_ref=(
                    hybrid_item.range_ref
                    if hybrid_item is not None
                    else locator.range_ref
                    if locator is not None
                    else None
                ),
                source_url=(
                    hybrid_item.source_url
                    if hybrid_item is not None
                    else locator.source_url
                    if locator is not None
                    else None
                ),
                statement_ids=strength_tuple[2] if strength_tuple is not None else (),
                content_kind=hybrid_item.content_kind
                if hybrid_item is not None
                else None,
                figure_id=hybrid_item.figure_id if hybrid_item is not None else None,
            )
        )
    scored.sort(key=lambda item: (-item.combined_score, item.chunk_id))
    return tuple(scored), discarded


def graph_branch_usable(fusion_input: FusionInput) -> tuple[bool, str | None]:
    """Decide whether resolved graph paths may contribute ranks.

    Args:
        fusion_input: Fusion inputs including survival and fallback.

    Returns:
        ``(usable, typed_reason)``. When unusable, Combined becomes Hybrid.
    """

    if fusion_input.graph_timeout:
        return False, "graph_timeout"
    reason = fusion_input.graph_fallback_reason
    if reason in GRAPH_DEGRADE_REASONS:
        return False, reason
    ratio = fusion_input.graph_survival_ratio
    if ratio is not None and ratio < FUSION_SURVIVAL_THRESHOLD:
        return False, "graph_survival_below_threshold"
    combined_like = fusion_input.effective_route in {"combined", "composite"}
    requested_combined = fusion_input.requested_route in {"combined", "composite"}
    if not combined_like and not requested_combined:
        return False, None
    if not fusion_input.graph_paths:
        return False, reason or "graph_empty"
    return True, None
