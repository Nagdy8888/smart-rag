"""Frozen Hybrid document/section quotas and the 40% graph-only cap."""

from __future__ import annotations

import math

from smart_rag_core.query_fusion.constants import (
    FUSION_DOCUMENT_QUOTA,
    FUSION_FINAL_EVIDENCE_MAX,
    FUSION_SECTION_QUOTA,
    GRAPH_DISCOVERED_ONLY_CAP,
)
from smart_rag_core.query_fusion.exceptions import FusionError
from smart_rag_core.query_fusion.models import ScoredPassage


def apply_document_section_quotas(
    ordered: tuple[ScoredPassage, ...],
    *,
    document_quota: int = FUSION_DOCUMENT_QUOTA,
    section_quota: int = FUSION_SECTION_QUOTA,
    limit: int = FUSION_FINAL_EVIDENCE_MAX,
) -> tuple[ScoredPassage, ...]:
    """Keep at most ``limit`` passages with per-document and per-section quotas.

    The frozen values (2 and 2) are a floor. When the pool has fewer distinct
    documents or first headings than ``limit / floor``, the effective quota
    rises so one document can fill the evidence limit. Six or more distinct
    documents keep the floor of 2.

    Args:
        ordered: Passages in Combined (or union) score/rank order.
        document_quota: Minimum passages per document. Frozen floor is 2.
        section_quota: Minimum passages per first heading. Frozen floor is 2.
        limit: Final evidence cap. Frozen at 12.

    Returns:
        Selected passages in input order.
    """

    distinct_docs = len({item.document_id for item in ordered})
    distinct_sections = len(
        {item.section_path[0] for item in ordered if item.section_path}
    )
    effective_doc_quota = max(document_quota, math.ceil(limit / max(1, distinct_docs)))
    effective_section_quota = (
        max(section_quota, math.ceil(limit / distinct_sections))
        if distinct_sections
        else section_quota
    )
    selected: list[ScoredPassage] = []
    doc_counts: dict[str, int] = {}
    section_counts: dict[str, int] = {}
    for item in ordered:
        if len(selected) >= limit:
            break
        if doc_counts.get(item.document_id, 0) >= effective_doc_quota:
            continue
        section = item.section_path[0] if item.section_path else ""
        if section and section_counts.get(section, 0) >= effective_section_quota:
            continue
        selected.append(item)
        doc_counts[item.document_id] = doc_counts.get(item.document_id, 0) + 1
        if section:
            section_counts[section] = section_counts.get(section, 0) + 1
    return tuple(selected)


def cap_graph_discovered_only(
    selected: tuple[ScoredPassage, ...],
    *,
    cap: float = GRAPH_DISCOVERED_ONLY_CAP,
) -> tuple[tuple[ScoredPassage, ...], tuple[str, ...]]:
    """Drop lowest-scoring graph-only passages until the 40% cap holds.

    Graph-only answer fallback is forbidden: if every remaining unit is
    graph-discovered-only, they are all dropped.

    Args:
        selected: Quota-trimmed passages.
        cap: Maximum graph-discovered-only fraction. Frozen at 0.40.

    Returns:
        Remaining passages and dropped graph-only chunk IDs.

    Raises:
        FusionError: If ``cap`` exceeds the frozen 40% allow-list.
    """

    if cap > GRAPH_DISCOVERED_ONLY_CAP + 1e-12:
        raise FusionError("graph_only_cap_above_40")
    remaining = list(selected)
    dropped: list[str] = []
    while remaining:
        graph_only = [item for item in remaining if item.graph_discovered_only]
        ratio = len(graph_only) / len(remaining)
        if ratio <= cap + 1e-12:
            break
        victim = min(
            graph_only,
            key=lambda item: (item.combined_score, item.chunk_id),
        )
        remaining = [item for item in remaining if item.chunk_id != victim.chunk_id]
        dropped.append(victim.chunk_id)
    return tuple(remaining), tuple(dropped)


def graph_only_ratio(selected: tuple[ScoredPassage, ...]) -> float:
    """Return graph-discovered-only / final count, or 0 when empty.

    Args:
        selected: Final evidence units.

    Returns:
        Ratio in ``[0, 1]``.
    """

    if not selected:
        return 0.0
    graph_only = sum(1 for item in selected if item.graph_discovered_only)
    return graph_only / len(selected)
