"""OpenAPI and member-denial tests for glossary import routes."""

from __future__ import annotations

import pytest

from tests.unit.typed_openapi import (
    as_openapi_client,
    json_object,
    openapi_test_client,
)


def test_glossary_routes_are_registered() -> None:
    """Glossary import, approve, and rollback appear in OpenAPI."""

    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    assert "/admin/glossary/imports" in paths
    assert "/admin/glossary/imports/{import_id}/approve" in paths
    assert "/admin/glossary/imports/{import_id}/rollback" in paths


def test_member_cannot_import_glossary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members cannot seed the private glossary."""

    monkeypatch.setenv("APP_ENV", "test")
    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        response = client.post(
            "/admin/glossary/imports",
            json={
                "source_name": "synthetic",
                "source_version": "v1",
                "idempotency_key": "member-forbidden-key",
                "entries": [
                    {
                        "entry_key": "inv-1",
                        "canonical_term": "INV-SR-8801",
                        "entry_type": "product_code",
                        "aliases": [{"alias": "invoice 8801", "language": "en"}],
                    }
                ],
            },
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert json_object(response.json())["detail"] == "forbidden"


def test_viewer_cannot_approve_glossary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Viewers cannot approve glossary imports."""

    monkeypatch.setenv("APP_ENV", "test")
    with openapi_test_client() as raw_client:
        client = as_openapi_client(raw_client)
        response = client.post(
            "/admin/glossary/imports/00000000-0000-4000-8000-000000000099/approve",
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000003",
                "X-Test-Role": "viewer",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert json_object(response.json())["detail"] == "forbidden"
