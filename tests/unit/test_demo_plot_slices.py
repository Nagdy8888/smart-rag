"""Unit tests for CMU plot-summary demo slice ranges."""

from __future__ import annotations

import pytest
from smart_rag_core.release.demo_corpus import (
    GRAPH_SLICE_LINE_COUNT,
    HYBRID_SLICE_LINE_COUNT,
    DemoPlotSliceError,
    cut_line_range,
)


def test_cut_line_range_takes_graph_then_hybrid_without_overlap() -> None:
    """Lines 1-200 and 201-1000 are disjoint and exact counts."""

    source = tuple(f"{index}\tplot-{index}" for index in range(1, 1201))
    graph = cut_line_range(source, start_line=1, count=GRAPH_SLICE_LINE_COUNT)
    hybrid = cut_line_range(source, start_line=201, count=HYBRID_SLICE_LINE_COUNT)
    assert len(graph) == 200
    assert len(hybrid) == 800
    assert graph[0] == "1\tplot-1"
    assert hybrid[0] == "201\tplot-201"
    assert hybrid[-1] == "1000\tplot-1000"
    graph_ids = {item.split("\t", 1)[0] for item in graph}
    hybrid_ids = {item.split("\t", 1)[0] for item in hybrid}
    assert not graph_ids & hybrid_ids


def test_cut_line_range_rejects_short_source() -> None:
    """A dump shorter than the hybrid window fails closed."""

    with pytest.raises(DemoPlotSliceError, match="too_short"):
        cut_line_range(("only-one",), start_line=1, count=200)
