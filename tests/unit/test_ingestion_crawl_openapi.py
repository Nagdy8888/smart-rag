"""OpenAPI and authorization tests for website crawl enqueue."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.main import create_app


def test_ingestion_crawl_route_is_registered() -> None:
    """Approved crawl enqueue appears in OpenAPI."""

    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()
    assert "/ingestion/crawls" in schema.get("paths", {})


def test_member_cannot_enqueue_website_crawl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members cannot broaden crawl scope."""

    monkeypatch.setenv("APP_ENV", "test")
    with TestClient(create_app()) as client:
        response = client.post(
            "/ingestion/crawls",
            json={
                "start_url": "https://example.test/docs",
                "approved_domain": "example.test",
                "idempotency_key": "crawl-member-forbidden-key",
            },
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
