"""OpenAPI contract for ingestion status routes."""

from __future__ import annotations

from typing import cast

import pytest

from tests.unit.typed_openapi import (
    as_openapi_client,
    json_object,
    openapi_test_client,
)


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
            nested_map = cast(dict[str, object], nested)
            props = nested_map.get("properties", {})
            return cast(dict[str, object], props) if isinstance(props, dict) else {}
    all_of = field_schema.get("allOf")
    if isinstance(all_of, list):
        for raw_part in cast(list[object], all_of):
            if isinstance(raw_part, dict) and "$ref" in raw_part:
                return _schema_properties(components, cast(dict[str, object], raw_part))
    props = field_schema.get("properties", {})
    return cast(dict[str, object], props) if isinstance(props, dict) else {}


def test_ingestion_status_routes_are_registered() -> None:
    """Status and retry routes appear in OpenAPI with nested diagnostics."""

    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    assert "/ingestion/versions/{version_id}/status" in paths
    assert "/ingestion/jobs/{job_id}/retry" in paths
    status_path = json_object(paths["/ingestion/versions/{version_id}/status"])
    status_get = json_object(status_path["get"])
    responses = json_object(status_get["responses"])
    ok_response = json_object(responses["200"])
    assert ok_response["description"]
    components = json_object(
        json_object(schema.get("components", {})).get("schemas", {})
    )
    version_schema = json_object(components.get("IngestionStatusResponse", {}))
    properties = json_object(version_schema.get("properties", {}))
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
    bm25_props = _schema_properties(components, json_object(bm25_schema))
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
    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        response = client.post(
            "/ingestion/jobs/00000000-0000-4000-8000-000000000001/retry",
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert json_object(response.json())["detail"] == "forbidden"
