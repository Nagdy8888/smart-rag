"""OpenAPI contract for ingestion status routes."""

from __future__ import annotations

from fastapi.testclient import TestClient
from smart_rag_api.main import create_app


def test_ingestion_status_routes_are_registered() -> None:
    """Status and retry routes appear in OpenAPI."""

    client = TestClient(create_app())
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/ingestion/versions/{version_id}/status" in paths
    assert "/ingestion/jobs/{job_id}/retry" in paths
    status_get = paths["/ingestion/versions/{version_id}/status"]["get"]
    assert status_get["responses"]["200"]["description"]
