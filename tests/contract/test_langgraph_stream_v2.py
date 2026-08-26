"""Pinned LangGraph 1.2.11 v2 multi-mode stream-shape contract."""

from __future__ import annotations

from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.version import __version__ as langgraph_version
from smart_rag_api.services.sse.stream_parts import (
    custom_mapping_from_part,
    parse_stream_part,
    updates_mapping_from_part,
)


class _ProbeState(TypedDict):
    """Minimal state used only to observe the installed stream shape."""

    value: int


def _increment(state: _ProbeState) -> _ProbeState:
    """Emit one custom start, then return the node update.

    Args:
        state: Probe graph state.

    Returns:
        Incremented value.
    """

    writer = get_stream_writer()
    writer({"kind": "node_start", "stage": "increment"})
    return {"value": state["value"] + 1}


def test_pinned_langgraph_v2_emits_custom_then_updates() -> None:
    """Installed 1.2.11 yields ``{type, ns, data}`` with custom before updates."""

    assert langgraph_version == "1.2.11"
    graph = StateGraph(_ProbeState)
    graph.add_node("increment", _increment)
    graph.add_edge(START, "increment")
    graph.add_edge("increment", END)
    compiled = graph.compile()
    raw_parts = list(
        compiled.stream(
            {"value": 0},
            stream_mode=["updates", "custom"],
            version="v2",
        )
    )
    assert [part["type"] for part in raw_parts] == ["custom", "updates"]
    assert all(part["ns"] == () for part in raw_parts)
    parsed = [parse_stream_part(part) for part in raw_parts]
    assert parsed[0] is not None
    assert parsed[1] is not None
    assert custom_mapping_from_part(parsed[0]) == {
        "kind": "node_start",
        "stage": "increment",
    }
    assert updates_mapping_from_part(parsed[1]) == {"increment": {"value": 1}}
