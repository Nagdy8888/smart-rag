"""Decode fusion, table, and memory mappings from query-graph state."""

from __future__ import annotations

from typing import cast

from smart_rag_core.query_answer.models import TableComposition
from smart_rag_core.query_fusion import SELECTED_FUSION_ALGORITHM
from smart_rag_core.query_fusion.models import FusionResult


def fusion_from_state(raw: object) -> FusionResult:
    """Rebuild fusion output from graph state.

    Args:
        raw: Mapping or None.

    Returns:
        Fusion result. Empty Hybrid-effective result when missing.
    """

    if raw is None:
        return FusionResult(
            algorithm=SELECTED_FUSION_ALGORITHM,
            config_hash="0" * 64,
            requested_route="hybrid",
            effective_route="hybrid",
            evidence=(),
            graph_discovered_only_ratio=0.0,
        )
    return FusionResult.model_validate(raw)


def tables_from_state(raw: object) -> TableComposition:
    """Rebuild table composition from graph state.

    Args:
        raw: Mapping or None.

    Returns:
        Table composition, empty when missing.
    """

    if raw is None:
        return TableComposition()
    return TableComposition.model_validate(raw)


def memory_text_from_state(raw: object) -> str:
    """Format bounded untrusted memory for general chat.

    Args:
        raw: ``memory_records`` list from graph state.

    Returns:
        Delimited memory text, or empty when none is present.
    """

    if not isinstance(raw, list):
        return ""
    parts: list[str] = []
    for item in cast(list[object], raw)[:8]:
        if not isinstance(item, dict):
            continue
        typed_item = {
            str(key): value for key, value in cast(dict[object, object], item).items()
        }
        role = str(typed_item.get("role") or "unknown")[:32]
        content = str(typed_item.get("content") or "")[:500]
        if not content:
            continue
        parts.append(f'<<untrusted-memory role="{role}">>{content}</untrusted-memory>')
    return "\n".join(parts)[:4000]
