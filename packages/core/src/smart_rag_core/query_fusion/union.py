"""Naive deduplicated union of Hybrid ranks and graph-resolved chunk IDs."""

from __future__ import annotations

from smart_rag_core.query_fusion.models import (
    FusionInput,
    GraphPassage,
    HybridPassage,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_fusion.ranking import (
    discard_unusable_paths,
    graph_branch_usable,
    usable_graph_passages,
    usable_hybrid_passages,
)


def score_naive_union(
    fusion_input: FusionInput,
) -> tuple[tuple[ScoredPassage, ...], tuple[str, ...]]:
    """Concatenate unique Hybrid IDs then surviving graph IDs without fusion scores.

    Hybrid order is preserved. Graph-discovered IDs append after Hybrid.
    Combined RRF and agreement are not applied. Quotas and the 40% cap are
    applied by the caller so ablation compares ranking, not quota policy.

    Args:
        fusion_input: Hybrid passages and resolved graph paths.

    Returns:
        Ordered scored passages using Hybrid-first ranks as ``combined_score``
        inverses, plus path discard reasons.
    """

    hybrid = usable_hybrid_passages(fusion_input.hybrid_passages)
    locators = usable_graph_passages(fusion_input.graph_passages)
    usable, _reason = graph_branch_usable(fusion_input)
    discarded: tuple[str, ...] = ()
    graph_ids: list[str] = []
    if usable:
        kept, discarded = discard_unusable_paths(
            fusion_input.graph_paths,
            steering_chunk_ids=frozenset(fusion_input.global_steering_chunk_ids),
        )
        seen_graph: set[str] = set()
        for path in kept:
            for chunk_id in path.canonical_chunk_ids:
                if chunk_id not in seen_graph:
                    seen_graph.add(chunk_id)
                    graph_ids.append(chunk_id)
    scored: list[ScoredPassage] = []
    seen: set[str] = set()
    for index, item in enumerate(hybrid):
        seen.add(item.chunk_id)
        scored.append(
            _from_hybrid(item, origin=PassageOrigin.HYBRID, position=index + 1)
        )
    for chunk_id in graph_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        locator = locators.get(chunk_id)
        scored.append(
            _from_graph_only(
                chunk_id,
                locator=locator,
                position=len(scored) + 1,
            )
        )
    return tuple(scored), discarded


def _from_hybrid(
    item: HybridPassage,
    *,
    origin: PassageOrigin,
    position: int,
) -> ScoredPassage:
    """Build a union row from one Hybrid passage.

    Args:
        item: Hybrid evidence.
        origin: Hybrid or both.
        position: 1-based union position used as a rank substitute.

    Returns:
        Scored passage without graph RRF.
    """

    return ScoredPassage(
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        version_id=item.version_id,
        citation_text=item.citation_text,
        hybrid_rank=item.hybrid_rank,
        graph_rank=None,
        combined_score=1.0 / position,
        origin=origin,
        graph_discovered_only=False,
        section_path=item.section_path,
        page_number=item.page_number,
        sheet_name=item.sheet_name,
        range_ref=item.range_ref,
        source_url=item.source_url,
        content_kind=item.content_kind,
        figure_id=item.figure_id,
        parent_chunk_id=item.parent_chunk_id,
    )


def _from_graph_only(
    chunk_id: str,
    *,
    locator: GraphPassage | None,
    position: int,
) -> ScoredPassage:
    """Build a union row for a graph-discovered chunk absent from Hybrid.

    Args:
        chunk_id: Canonical chunk UUID string.
        locator: Optional canonical locator.
        position: 1-based union position.

    Returns:
        Graph-discovered-only scored passage.
    """

    return ScoredPassage(
        chunk_id=chunk_id,
        document_id=locator.document_id if locator is not None else chunk_id,
        version_id=locator.version_id if locator is not None else chunk_id,
        citation_text=locator.citation_text if locator is not None else "",
        hybrid_rank=None,
        graph_rank=position,
        combined_score=1.0 / position,
        origin=PassageOrigin.GRAPH_RESOLVED,
        graph_discovered_only=True,
        section_path=locator.section_path if locator is not None else (),
        page_number=locator.page_number if locator is not None else None,
        sheet_name=locator.sheet_name if locator is not None else None,
        range_ref=locator.range_ref if locator is not None else None,
        source_url=locator.source_url if locator is not None else None,
    )
