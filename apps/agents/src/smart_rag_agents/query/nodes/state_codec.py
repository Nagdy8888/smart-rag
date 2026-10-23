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


def memory_text_from_state(raw: object, *, max_chars: int = 8000) -> str:
    """Format bounded untrusted memory for general chat.

    Args:
        raw: ``memory_records`` list from graph state.
        max_chars: Prompt-specific bound, preserving summary and newest messages.

    Returns:
        Delimited memory text, or empty when none is present.
    """

    if not isinstance(raw, list):
        return ""
    summaries: list[str] = []
    recent: list[str] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            continue
        typed_item = {
            str(key): value for key, value in cast(dict[object, object], item).items()
        }
        role = str(typed_item.get("role") or "unknown").replace('"', "")[:32]
        content = str(typed_item.get("content") or "")[:1500]
        content = content.replace("<<", "").replace(">>", "")
        if not content:
            continue
        block = f'<<untrusted-memory role="{role}">>{content}</untrusted-memory>'
        (summaries if role == "system" else recent).append(block)
    # Preserve the complete compact summary, then the newest complete messages.
    # A per-record 500-character cut used to erase late user constraints.
    parts = summaries[:1]
    size = sum(map(len, parts))
    kept: list[str] = []
    for block in reversed(recent):
        if size + len(block) + 1 > max_chars:
            break
        kept.append(block)
        size += len(block) + 1
    return "\n".join([*parts, *reversed(kept)])
