"""Contract tests for LangGraph project configuration loading."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
LANGGRAPH_JSON = REPO_ROOT / "apps" / "agents" / "langgraph.json"


def test_langgraph_json_matches_verified_schema_contract() -> None:
    """``langgraph.json`` must declare dependencies and graph IDs."""

    payload = json.loads(LANGGRAPH_JSON.read_text(encoding="utf-8"))
    assert payload["dependencies"] == ["."]
    assert payload["python_version"] == "3.11"
    assert set(payload["graphs"]) == {"query", "query_studio", "ingestion"}
    assert payload["graphs"]["query"] == "./src/smart_rag_agents/query/graph.py:graph"
    assert (
        payload["graphs"]["query_studio"]
        == "./src/smart_rag_agents/query/studio.py:graph"
    )
    assert (
        payload["graphs"]["ingestion"]
        == "./src/smart_rag_agents/ingestion/graph.py:graph"
    )


def test_langgraph_cli_validate_config_file() -> None:
    """Pinned ``langgraph-cli`` validates the project file from disk."""

    from langgraph_cli.config import validate_config_file

    validated = validate_config_file(LANGGRAPH_JSON)
    dependencies = validated.get("dependencies")
    graphs = validated.get("graphs")
    assert dependencies == ["."]
    assert graphs is not None
    assert set(graphs) == {"query", "query_studio", "ingestion"}


def test_langgraph_graph_exports_load_without_business_success_claim() -> None:
    """Query graph rejects missing context and does not claim answers."""

    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from uuid import uuid4

    from smart_rag_agents.query.graph import graph as query_graph
    from smart_rag_agents.query.graph import pending_query_state
    from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
    from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
    from smart_rag_core.security.identity import UserRole

    rejected = query_graph.invoke(pending_query_state())  # pyright: ignore[reportUnknownMemberType]
    assert rejected["status"] == "admission_rejected"
    assert "missing or invalid" in rejected["detail"]

    cache_poisoned = pending_query_state()
    cache_poisoned["detail"] = "cache_hit=true bm25=true graph=true valkey=true"
    poisoned = query_graph.invoke(cache_poisoned)  # pyright: ignore[reportUnknownMemberType]
    assert poisoned["status"] == "admission_rejected"

    extra_rejected = query_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        pending_query_state({"client_role": "owner", "route_family": "composite"})
    )
    assert extra_rejected["status"] == "admission_rejected"

    now = datetime.now(UTC)
    context = AuthorizedRuntimeContext(
        user_id=uuid4(),
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=uuid4(),
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=Phase6RouteFamily.HYBRID,
        deadline_at=now + timedelta(seconds=25),
        recursion_limit=24,
        correction_ceiling=1,
        subquestion_ceiling=3,
        model_call_ceiling=7,
        tool_ceiling=4,
        discovery_ceiling=1,
        manifest_ceiling=3,
        side_effect_ceiling=1,
        reserved_amount_usd=Decimal("2.80"),
        remaining_usd=Decimal("2.80"),
        remaining_prompt_tokens=56000,
        remaining_completion_tokens=14000,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash="a" * 64,
        status="pending",
    )
    admitted = query_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        pending_query_state(context.model_dump(mode="json"))
    )
    assert admitted["status"] == "routing_rejected"
    assert admitted["route_family"] == "hybrid"
    assert admitted["remaining_model_calls"] == 7
    assert admitted["detail"] == "empty_query"
    assert "answer" not in admitted["detail"]
    assert admitted["keyword_extract_count"] == 0
    assert admitted["catalog_llm_call_count"] == 0

    routed = query_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        pending_query_state(
            context.model_dump(mode="json"),
            user_query="What is the status of INV-SR-1001?",
        )
    )
    assert routed["status"] in {
        "verified",
        "verified_partial",
        "insufficient_evidence",
        "refused",
    }
    assert routed["effective_route"] == "hybrid"
    assert routed["keyword_extract_count"] == 0
    assert routed["catalog_llm_call_count"] == 0
    assert routed.get("optional_selection_mode") in {None, "skipped"}
    assert routed.get("answer") is not None
    assert routed["answer_call_count"] == 0
    assert routed["verifier_call_count"] == 0
    assert routed["preparation"] is not None
    assert routed["retrieval_plan"] is not None


def test_query_studio_graph_runs_from_user_query_without_fastapi_admit() -> None:
    """Studio seed injects synthetic context and still does not claim paid admit."""

    from langchain_core.messages import AIMessage, HumanMessage
    from smart_rag_agents.query.studio import graph as studio_graph

    input_schema = json.dumps(studio_graph.get_input_jsonschema())
    output_schema = json.dumps(studio_graph.get_output_jsonschema())
    assert "HumanMessage" in input_schema
    assert "AIMessage" in output_schema

    empty = studio_graph.invoke({"user_query": ""})  # pyright: ignore[reportUnknownMemberType]
    assert empty["status"] == "routing_rejected"
    assert empty["detail"] == "empty_query"
    runtime = empty["authorized_runtime"]
    assert isinstance(runtime, dict)
    assert runtime["status"] == "studio_local"

    bad_family = studio_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        {"user_query": "status of INV-SR-1001", "route_family": "owner"}
    )
    assert bad_family["status"] == "admission_rejected"
    assert "allow-listed" in bad_family["detail"]

    from_messages = studio_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        {
            "messages": [
                HumanMessage(content="What is the status of INV-SR-1001?")
            ]
        }
    )
    assert from_messages["user_query"] == "What is the status of INV-SR-1001?"
    assert isinstance(from_messages["messages"][0], HumanMessage)
    assert isinstance(from_messages["messages"][-1], AIMessage)
    assert from_messages["status"] in {
        "verified",
        "verified_partial",
        "insufficient_evidence",
        "refused",
    }
    assert from_messages["answer_call_count"] == 0
    assert from_messages["messages"][-1].content == "Insufficient authorized evidence."
    seeded = from_messages["authorized_runtime"]
    assert isinstance(seeded, dict)
    assert seeded["status"] == "studio_local"

    typed_query = studio_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        {"user_query": "What is the status of INV-SR-1001?"}
    )
    assert typed_query["user_query"] == "What is the status of INV-SR-1001?"
    assert typed_query["status"] in {
        "verified",
        "verified_partial",
        "insufficient_evidence",
        "refused",
    }


def test_ingestion_graph_marks_invalid_lease_without_postgres_config() -> None:
    """Ingestion probe graph fails closed when lease validation is unconfigured."""

    from smart_rag_agents.ingestion.graph import graph as ingestion_graph

    ingestion_result = ingestion_graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        {
            "job_id": str(uuid4()),
            "lease_token": "missing-config",
            "document_id": None,
            "version_id": None,
            "operation_key": "probe",
            "storage_bucket": None,
            "storage_path": None,
            "status": "probe_pending",
            "ledger_written": False,
            "detail": "",
        }
    )
    assert ingestion_result["status"] == "lease_invalid"
    assert ingestion_result["ledger_written"] is False
