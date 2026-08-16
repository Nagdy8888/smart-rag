"""Optional-tool telemetry that never exposes hidden catalog entries."""

from __future__ import annotations

from smart_rag_core.tools.models import OptionalTelemetry, SelectionPolicy


def build_telemetry(
    *,
    discovery_latency_ms: float,
    retrieval_latency_ms: float = 0.0,
    tools_searched: int,
    tools_disclosed: int,
    tools_loaded: int,
    tools_called: int,
    tools_rejected: int,
    tools_useful: int,
    selection_mode: SelectionPolicy,
    catalog_llm_call_count: int,
) -> OptionalTelemetry:
    """Build telemetry from visible-set counters only.

    Args:
        discovery_latency_ms: Catalog path latency.
        retrieval_latency_ms: Retrieval latency for contrast. Not mixed in.
        tools_searched: Visible tools considered.
        tools_disclosed: Level 1 cards shown.
        tools_loaded: Manifests loaded.
        tools_called: Executor attempts.
        tools_rejected: Executor rejections.
        tools_useful: Successful executions.
        selection_mode: Mapping, discovery, or skipped.
        catalog_llm_call_count: ``0`` or ``1``.

    Returns:
        Frozen telemetry. Hidden names and hidden counts are absent.
    """

    llm_calls: int = 1 if catalog_llm_call_count else 0
    return OptionalTelemetry(
        discovery_latency_ms=discovery_latency_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        tools_searched=tools_searched,
        tools_disclosed=tools_disclosed,
        tools_loaded=tools_loaded,
        tools_called=tools_called,
        tools_rejected=tools_rejected,
        tools_useful=tools_useful,
        selection_mode=selection_mode,
        catalog_llm_call_count=0 if llm_calls == 0 else 1,
    )
