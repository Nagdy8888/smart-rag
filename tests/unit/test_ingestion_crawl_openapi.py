"""OpenAPI and authorization tests for website crawl enqueue."""

from __future__ import annotations

import pytest

from tests.unit.typed_openapi import (
    as_openapi_client,
    json_object,
    openapi_test_client,
    permit_test_identity,
)


def test_ingestion_crawl_route_is_registered() -> None:
    """Approved crawl enqueue appears in OpenAPI."""

    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        schema = json_object(client.get("/openapi.json").json())
    assert "/ingestion/crawls" in json_object(schema.get("paths", {}))


def test_member_cannot_enqueue_website_crawl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members cannot broaden crawl scope."""

    permit_test_identity(monkeypatch)
    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
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
    assert json_object(response.json())["detail"] == "forbidden"
