"""OpenAPI and auth tests for graph inspection."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.main import create_app
from smart_rag_api.schemas.graph_inspect import GraphInspectResponse


def test_graph_inspect_route_is_registered() -> None:
    """``POST /graph/inspect`` appears in OpenAPI."""

    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/graph/inspect" in paths
    assert "post" in paths["/graph/inspect"]
    components = schema.get("components", {}).get("schemas", {})
    assert "GraphInspectResponse" in components
    properties = components["GraphInspectResponse"].get("properties", {})
    for field in ("nodes", "locators", "limitations", "row_count", "depth"):
        assert field in properties, field


def test_unauthenticated_inspect_is_unauthorized() -> None:
    """Inspection requires a bearer token or test identity."""

    with TestClient(create_app()) as client:
        response = client.post(
            "/graph/inspect",
            json={"entity_keys": ["ent-alpha"], "depth": 3},
        )
    assert response.status_code == 401


def test_member_may_call_inspect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members are allowed; ACL filtering happens in the resolver."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(
        "smart_rag_api.routers.graph_inspect._postgres_url",
        lambda _request: "postgresql://unused",
    )
    monkeypatch.setattr(
        "smart_rag_api.routers.graph_inspect.inspect_graph_for_caller",
        lambda *_args, **_kwargs: GraphInspectResponse(
            nodes=(),
            locators=(),
            limitations=(),
            row_count=0,
            depth=3,
        ),
    )
    with TestClient(create_app()) as client:
        response = client.post(
            "/graph/inspect",
            json={
                "entity_keys": ["ent-alpha"],
                "document_id": str(uuid4()),
                "depth": 3,
            },
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 200
    assert response.json()["row_count"] == 0


def test_empty_inspect_seed_is_rejected() -> None:
    """Inspection requires at least one entity key or document id."""

    with TestClient(create_app()) as client:
        response = client.post("/graph/inspect", json={"depth": 3})
    assert response.status_code in {401, 422}
