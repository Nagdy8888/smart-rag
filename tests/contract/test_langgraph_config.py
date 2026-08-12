"""Contract tests for LangGraph project configuration loading."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LANGGRAPH_JSON = REPO_ROOT / "apps" / "agents" / "langgraph.json"


def test_langgraph_json_matches_verified_schema_contract() -> None:
    """``langgraph.json`` must declare dependencies and both graph IDs."""

    payload = json.loads(LANGGRAPH_JSON.read_text(encoding="utf-8"))
    assert payload["dependencies"] == ["."]
    assert set(payload["graphs"]) == {"query", "ingestion"}
    assert (
        payload["graphs"]["query"]
        == "./src/smart_rag_agents/query/graph.py:graph"
    )
    assert (
        payload["graphs"]["ingestion"]
        == "./src/smart_rag_agents/ingestion/graph.py:graph"
    )


def test_langgraph_cli_validate_config_file() -> None:
    """Pinned ``langgraph-cli`` validates the project file from disk."""

    from langgraph_cli.config import validate_config_file

    validated = validate_config_file(LANGGRAPH_JSON)
    assert validated["dependencies"] == ["."]
    assert set(validated["graphs"]) == {"query", "ingestion"}


def test_langgraph_graph_exports_load_without_business_success_claim() -> None:
    """Graph exports import and compile; invoke only returns unconfigured."""

    from smart_rag_agents.ingestion.graph import graph as ingestion_graph
    from smart_rag_agents.query.graph import graph as query_graph

    query_result = query_graph.invoke({"status": "unconfigured", "detail": ""})
    ingestion_result = ingestion_graph.invoke(
        {"status": "unconfigured", "detail": ""}
    )
    assert query_result["status"] == "unconfigured"
    assert "not implemented" in query_result["detail"]
    assert ingestion_result["status"] == "unconfigured"
    assert "not implemented" in ingestion_result["detail"]
