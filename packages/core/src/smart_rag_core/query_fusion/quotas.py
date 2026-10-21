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


_NATIVE_KINDS = frozenset({"code", "table", "figure"})


def reserve_native_passages(
    ordered: tuple[ScoredPassage, ...],
    selected: tuple[ScoredPassage, ...],
    *,
    limit: int = FUSION_FINAL_EVIDENCE_MAX,
) -> tuple[ScoredPassage, ...]:
    """Keep hybrid code, table, and figure passages inside the evidence cap.

    Rank weights are unchanged. A native passage that quotas left out
    replaces the lowest-scoring non-native passage, and a passage on
    another page is dropped before one on the native passage's page.

    Args:
        ordered: Passages in score order, before the cap dropped any.
        selected: Passages already kept by document and section quotas.
        limit: Final evidence cap. Frozen at 12.

    Returns:
        Selected passages in ``ordered`` sequence, at most ``limit`` items.
        Native graph-only passages are not reserved.
    """

    if limit < 1:
        return ()
    chosen = list(selected[:limit])
    chosen_ids = {item.chunk_id for item in chosen}
    missing = [
        item
        for item in ordered
        if item.content_kind in _NATIVE_KINDS
        and not item.graph_discovered_only
        and item.citation_text.strip()
        and item.chunk_id not in chosen_ids
    ]
    for native in missing:
        if len(chosen) < limit:
            chosen.append(native)
            chosen_ids.add(native.chunk_id)
            continue
        prose = [item for item in chosen if item.content_kind not in _NATIVE_KINDS]
        if not prose:
            break
        victim = min(prose, key=lambda item: _native_drop_key(item, native.page_number))
        chosen = [item for item in chosen if item.chunk_id != victim.chunk_id]
        chosen.append(native)
        chosen_ids.add(native.chunk_id)
    order = {item.chunk_id: index for index, item in enumerate(ordered)}
    chosen.sort(key=lambda item: order.get(item.chunk_id, limit + 1))
    return tuple(chosen[:limit])


def _native_drop_key(
    item: ScoredPassage, native_page: int | None
) -> tuple[int, float, str]:
    """Sort key for the prose passage a native block should replace.

    Args:
        item: Non-native passage currently inside the cap.
        native_page: Page of the native passage being reserved.

    Returns:
        Other-page prose sorts first, then lower score, then chunk id.
    """

    other_page = 0 if item.page_number != native_page else 1
    return (other_page, item.combined_score, item.chunk_id)


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
