"""OpenAPI contract for ingestion status routes."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from smart_rag_api.dependencies.services import get_postgres_url
from smart_rag_api.main import create_app
from smart_rag_api.routers.ingestion_status import get_ingestion_status_service
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext

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
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    with TestClient(application) as raw_client:
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


class _MissingStatusService:
    """Status service that treats every version as missing."""

    def get_version_status(
        self,
        caller: CallerContext,
        *,
        version_id: UUID,
    ) -> None:
        """Always hide existence.

        Args:
            caller: Authenticated caller.
            version_id: Requested version.

        Raises:
            QueryAdmissionError: Always ``not_found``.
        """

        del caller, version_id
        raise QueryAdmissionError("not_found")


def test_ingestion_status_unauthorized_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unauthorized or missing versions are HTTP 404, not 403."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    application = create_app()
    application.dependency_overrides[get_ingestion_status_service] = lambda: (
        _MissingStatusService()
    )
    with TestClient(application) as raw_client:
        client = as_openapi_client(raw_client)
        response = client.get(
            f"/ingestion/versions/{uuid4()}/status",
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 404
    assert json_object(response.json())["detail"] == "not_found"


def test_detector_review_route_is_registered() -> None:
    """Owner/admin review transport appears in the public OpenAPI surface."""

    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    assert "/ingestion/detector-findings/reviews" in paths
    review_path = json_object(paths["/ingestion/detector-findings/reviews"])
    assert "post" in review_path
    version_schema = json_object(
        json_object(json_object(schema.get("components", {})).get("schemas", {})).get(
            "ReviewDiagnostics", {}
        )
    )
    properties = json_object(version_schema.get("properties", {}))
    assert "finding_count" in properties
    assert "findings" in properties


class _MissingReviewService:
    """Review service that hides every finding as missing."""

    def review_finding(
        self,
        caller: CallerContext,
        *,
        finding_id: UUID,
        decision: str,
        reason: str,
        idempotency_key: str,
    ) -> None:
        """Always hide existence.

        Args:
            caller: Authenticated caller.
            finding_id: Requested finding.
            decision: Unused decision.
            reason: Unused reason.
            idempotency_key: Unused replay key.

        Raises:
            QueryAdmissionError: Always ``not_found``.
        """

        del caller, finding_id, decision, reason, idempotency_key
        raise QueryAdmissionError("not_found")


def test_member_detector_review_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Members and viewers cannot distinguish missing from unauthorized findings."""

    from smart_rag_api.routers.governance_reviews import get_governance_review_service

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    application = create_app()
    application.dependency_overrides[get_postgres_url] = lambda: "postgresql://unused"
    application.dependency_overrides[get_governance_review_service] = lambda: (
        _MissingReviewService()
    )
    with TestClient(application) as raw_client:
        client = as_openapi_client(raw_client)
        response = client.post(
            "/ingestion/detector-findings/reviews",
            json={
                "finding_id": str(uuid4()),
                "decision": "false_positive",
                "reason": "not a secret",
                "idempotency_key": "idem-key-01",
            },
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 404
    assert json_object(response.json())["detail"] == "not_found"
