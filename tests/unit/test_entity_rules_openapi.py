"""OpenAPI and member-denial tests for graph entity-rule routes."""

from __future__ import annotations

import pytest

from tests.unit.typed_openapi import (
    as_openapi_client,
    json_object,
    openapi_test_client,
)


def test_entity_rule_routes_are_registered() -> None:
    """Owner/admin entity-rule CRUD appears in OpenAPI."""

    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    assert "/admin/graph/entity-rules" in paths
    assert "/admin/graph/entity-rules/suggestions" in paths
    assert "/admin/graph/entity-rules/{rule_id}/approve" in paths
    assert "/admin/graph/entity-rules/{rule_id}/revoke" in paths


def test_member_cannot_create_entity_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members cannot mutate graph entity rules."""

    monkeypatch.setenv("APP_ENV", "test")
    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        response = client.post(
            "/admin/graph/entity-rules",
            json={
                "entity_type": "PROJECT",
                "canonical_name": "Atlas",
                "aliases": ["ATLAS"],
            },
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert json_object(response.json())["detail"] == "forbidden"


def test_viewer_cannot_approve_entity_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Viewers cannot approve suggestions."""

    monkeypatch.setenv("APP_ENV", "test")
    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        response = client.post(
            "/admin/graph/entity-rules/00000000-0000-4000-8000-000000000099/approve",
            json={"row_version": 1},
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000003",
                "X-Test-Role": "viewer",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert json_object(response.json())["detail"] == "forbidden"
