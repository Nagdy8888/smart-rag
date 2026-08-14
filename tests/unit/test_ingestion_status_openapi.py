"""OpenAPI contract for ingestion status routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.main import create_app


def test_ingestion_status_routes_are_registered() -> None:
    """Status and retry routes appear in OpenAPI."""

    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/ingestion/versions/{version_id}/status" in paths
    assert "/ingestion/jobs/{job_id}/retry" in paths
    status_get = paths["/ingestion/versions/{version_id}/status"]["get"]
    assert status_get["responses"]["200"]["description"]


def test_member_retry_is_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members cannot invoke ingestion job retry actions."""

    monkeypatch.setenv("APP_ENV", "test")
    with TestClient(create_app()) as client:
        response = client.post(
            "/ingestion/jobs/00000000-0000-4000-8000-000000000001/retry",
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
