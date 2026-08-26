"""Bound query nodes preserve production stage names and route topology."""

from __future__ import annotations

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.graph import (
    build_query_graph,
    production_stage_names,
)
from smart_rag_agents.query.runtime.bound_nodes import bind_query_nodes


def test_bound_nodes_expose_every_production_wrapper() -> None:
    """Each production stage except admission has a bound callable."""

    bound = bind_query_nodes(QueryGraphDeps())
    expected = set(production_stage_names()) - {"enforce_admission"}
    assert set(bound.__dataclass_fields__) == expected


def test_production_and_studio_graphs_register_the_same_core_stages() -> None:
    """Studio compile adds seed/emit nodes without renaming core stages."""

    expected = set(production_stage_names())
    production = set(build_query_graph().compile().get_graph().nodes)
    local = set(build_query_graph(studio_local=True).compile().get_graph().nodes)
    live = set(build_query_graph(studio_live=True).compile().get_graph().nodes)
    assert expected <= production
    assert expected <= local
    assert expected <= live
    assert "seed_studio_runtime" in local
    assert "seed_studio_live_runtime" in live
    assert "emit_studio_response" in local
    assert "emit_studio_response" in live


def test_bound_nodes_module_has_no_topology_edges() -> None:
    """The binding owner must not import graph edges or stream writers."""

    from pathlib import Path

    from smart_rag_agents.query.runtime import bound_nodes as bound_mod

    path = Path(bound_mod.__file__ or "")
    body = path.read_text(encoding="utf-8")
    assert "add_edge" not in body
    assert "get_stream_writer" not in body
    assert "add_conditional_edges" not in body
