"""Unit tests for Graph-200 one-shot rebuild flags and Graph Ready checks."""

from __future__ import annotations

from scripts.ops.rebuild_demo_graph_canonical_passages import (
    EXPECTED_PASSAGE_COUNT,
    graph_ready_failed_invariant,
    parse_rebuild_args,
)


def test_parse_rebuild_args_defaults_to_full_rebuild() -> None:
    """Omitting flags keeps vendor-delete rebuild as an explicit choice."""

    args = parse_rebuild_args([])
    assert args.map_only is False


def test_parse_rebuild_args_map_only() -> None:
    """``--map-only`` skips vendor deletes and re-extract."""

    args = parse_rebuild_args(["--map-only"])
    assert args.map_only is True


def test_graph_ready_invariants_require_active_pointer_maps() -> None:
    """Graph Ready counts maps on the active pointer workspace only."""

    ready = {
        "version_status": "graph_ready",
        "pointer_workspace_key": "company_default__rebuild",
        "pointer_workspace_state": "active",
        "chunk_map_count": EXPECTED_PASSAGE_COUNT,
        "job_status": "completed",
    }
    assert graph_ready_failed_invariant(ready) is None
    leftover_live = {
        **ready,
        "pointer_workspace_key": "company_default",
        "pointer_workspace_state": "quarantined",
        "chunk_map_count": 87,
        "version_status": "graph_pending",
        "job_status": "completed",
    }
    assert (
        graph_ready_failed_invariant(leftover_live)
        == "version_status:graph_pending"
    )
    mixed_count = {
        **ready,
        "chunk_map_count": 87 + EXPECTED_PASSAGE_COUNT,
    }
    assert (
        graph_ready_failed_invariant(mixed_count)
        == f"chunk_map_count:{87 + EXPECTED_PASSAGE_COUNT}"
    )
    inactive_pointer = {
        **ready,
        "pointer_workspace_state": "building",
    }
    assert (
        graph_ready_failed_invariant(inactive_pointer)
        == "pointer_workspace_state:building"
    )
