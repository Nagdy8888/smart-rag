"""Contract tests for committed CMU plot demo slices."""

from __future__ import annotations

from pathlib import Path

from smart_rag_core.release.demo_corpus import (
    GRAPH_SLICE_FILENAME,
    GRAPH_SLICE_LINE_COUNT,
    HYBRID_SLICE_FILENAME,
    HYBRID_SLICE_LINE_COUNT,
    SOURCE_FILENAME,
    movie_summaries_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_demo_slices_match_operator_counts() -> None:
    """Graph-200 and hybrid-800 files exist, do not overlap, and are not the dump."""

    dataset = movie_summaries_dir(REPO_ROOT)
    source = (dataset / SOURCE_FILENAME).read_text(encoding="utf-8").splitlines()
    graph = (dataset / GRAPH_SLICE_FILENAME).read_text(encoding="utf-8").splitlines()
    hybrid = (dataset / HYBRID_SLICE_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(graph) == GRAPH_SLICE_LINE_COUNT
    assert len(hybrid) == HYBRID_SLICE_LINE_COUNT
    assert graph == source[0:200]
    assert hybrid == source[200:1000]
    assert len(source) > 1000
    graph_ids = {item.split("\t", 1)[0] for item in graph}
    hybrid_ids = {item.split("\t", 1)[0] for item in hybrid}
    assert not graph_ids & hybrid_ids
    assert GRAPH_SLICE_FILENAME != SOURCE_FILENAME
    assert HYBRID_SLICE_FILENAME != SOURCE_FILENAME
