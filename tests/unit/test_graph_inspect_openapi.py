"""OpenAPI and auth tests for graph inspection."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from httpx import Response
from smart_rag_api.main import create_app
from smart_rag_api.schemas.graph_inspect import (
    GraphInspectRequest,
    GraphInspectResponse,
)
from smart_rag_core.security.identity import CallerContext


class _TestHttpClient(Protocol):
    """Typed TestClient surface used by inspection OpenAPI tests."""

    def get(self, url: str) -> Response:
        """Send a GET request.

        Args:
            url: Request path.

        Returns:
            HTTPX response.
        """

        ...

    def post(
        self,
        url: str,
        *,
        json: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Send a POST request.

        Args:
            url: Request path.
            json: JSON body.
            headers: Optional HTTP headers.

        Returns:
            HTTPX response.
        """

        ...


def _http_client(client: TestClient) -> _TestHttpClient:
    """Mark a FastAPI TestClient as having typed HTTP methods.

    Args:
        client: Starlette/FastAPI test client.

    Returns:
        The same client with typed get/post.
    """

    return cast(_TestHttpClient, client)


def _object_map(value: object) -> dict[str, object]:
    """Treat a JSON value as an object map for OpenAPI assertions.

    Args:
        value: Decoded JSON value.

    Returns:
        The value as a string-key object map.
    """

    return cast(dict[str, object], value)


def _unused_postgres_url(_request: Request) -> str:
    """Return a dummy URL so inspection never opens Postgres.

    Args:
        _request: Incoming FastAPI request.

    Returns:
        Unused PostgreSQL URL.
    """

    del _request
    return "postgresql://unused"


def _empty_inspect(
    _postgres_url: str,
    *,
    caller: CallerContext,
    body: GraphInspectRequest,
    remaining_deadline_seconds: float,
) -> GraphInspectResponse:
    """Return an empty authorized inspection payload.

    Args:
        _postgres_url: Unused database URL.
        caller: Authenticated caller.
        body: Validated inspection seed.
        remaining_deadline_seconds: Remaining inspection deadline.

    Returns:
        Empty inspect response at depth 3.
    """

    del _postgres_url, caller, body, remaining_deadline_seconds
    return GraphInspectResponse(
        nodes=(),
        locators=(),
        limitations=(),
        row_count=0,
        depth=3,
    )


def test_graph_inspect_route_is_registered() -> None:
    """``POST /graph/inspect`` appears in OpenAPI."""

    with TestClient(create_app()) as raw:
        client = _http_client(raw)
        schema = _object_map(client.get("/openapi.json").json())
    paths = _object_map(schema.get("paths", {}))
    assert "/graph/inspect" in paths
    assert "post" in _object_map(paths["/graph/inspect"])
    components = _object_map(
        _object_map(schema.get("components", {})).get("schemas", {})
    )
    assert "GraphInspectResponse" in components
    properties = _object_map(
        _object_map(components["GraphInspectResponse"]).get("properties", {})
    )
    for field in ("nodes", "locators", "limitations", "row_count", "depth"):
        assert field in properties, field


def test_unauthenticated_inspect_is_unauthorized() -> None:
    """Inspection requires a bearer token or test identity."""

    with TestClient(create_app()) as raw:
        client = _http_client(raw)
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
        _unused_postgres_url,
    )
    monkeypatch.setattr(
        "smart_rag_api.routers.graph_inspect.inspect_graph_for_caller",
        _empty_inspect,
    )
    with TestClient(create_app()) as raw:
        client = _http_client(raw)
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
    assert _object_map(response.json())["row_count"] == 0


def test_empty_inspect_seed_is_rejected() -> None:
    """Inspection requires at least one entity key or document id."""

    with TestClient(create_app()) as raw:
        client = _http_client(raw)
        response = client.post("/graph/inspect", json={"depth": 3})
    assert response.status_code in {401, 422}
