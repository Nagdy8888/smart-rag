"""OpenAPI contract for ingestion status routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.main import create_app


def _schema_properties(
    components: dict[str, object], field_schema: dict[str, object]
) -> dict[str, object]:
    """Resolve OpenAPI ``$ref`` / ``allOf`` to a properties map.

    Args:
        components: OpenAPI ``components.schemas`` object.
        field_schema: Property schema that may be a ``$ref`` or ``allOf``.

    Returns:
        Nested ``properties`` dict for the referenced model.
    """

    ref = field_schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        nested = components.get(name, {})
        if isinstance(nested, dict):
            props = nested.get("properties", {})
            return props if isinstance(props, dict) else {}
    all_of = field_schema.get("allOf")
    if isinstance(all_of, list):
        for part in all_of:
            if isinstance(part, dict) and "$ref" in part:
                return _schema_properties(components, part)
    props = field_schema.get("properties", {})
    return props if isinstance(props, dict) else {}


def test_ingestion_status_routes_are_registered() -> None:
    """Status and retry routes appear in OpenAPI with nested diagnostics."""

    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/ingestion/versions/{version_id}/status" in paths
    assert "/ingestion/jobs/{job_id}/retry" in paths
    status_get = paths["/ingestion/versions/{version_id}/status"]["get"]
    assert status_get["responses"]["200"]["description"]
    components = schema.get("components", {}).get("schemas", {})
    version_schema = components.get("IngestionStatusResponse", {})
    properties = version_schema.get("properties", {})
    for field in (
        "status",
        "scan",
        "review",
        "ocr",
        "chunks_tables",
        "embedding",
        "bm25",
        "queue_age",
        "graph_handoff",
        "retry_allowed",
    ):
        assert field in properties, field
    bm25_schema = properties["bm25"]
    assert isinstance(bm25_schema, dict)
    bm25_props = _schema_properties(components, bm25_schema)
    for field in (
        "active_index_version",
        "lag_seconds",
        "dead_letter",
        "retry_attempts",
    ):
        assert field in bm25_props, field


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
