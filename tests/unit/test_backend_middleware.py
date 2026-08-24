"""Unit tests for backend correlation middleware and honest readiness."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, cast

import pytest
from fastapi import Request, Response
from smart_rag_api.middleware.request_limits import limit_request_body
from starlette.types import Scope

from tests.unit.test_settings import configure_hosted_backend_env


def _json_object(value: object) -> dict[str, object]:
    """Narrow decoded JSON to a string-keyed object.

    Args:
        value: Decoded JSON value.

    Returns:
        String-keyed mapping.

    Raises:
        TypeError: If ``value`` is not a JSON object.
    """

    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    return cast(dict[str, object], value)


def _http_app() -> tuple[Any, Any, Any]:
    """Lazy-import FastAPI test helpers so collection survives unrelated cycles.

    Returns:
        ``(TestClient, create_app, as_openapi_client)``.
    """

    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app

    from tests.unit.typed_openapi import as_openapi_client

    return TestClient, create_app, as_openapi_client


def _request(request_id: str) -> Request:
    """Build a typed in-memory HTTP request.

    Args:
        request_id: Caller correlation header value.

    Returns:
        Starlette request with no body or network transport.
    """

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
        "method": "GET",
        "root_path": "",
        "path": "/health/ready",
        "raw_path": b"/health/ready",
        "query_string": b"",
        "headers": [(b"x-request-id", request_id.encode("ascii"))],
        "state": {},
    }
    return Request(scope)


async def _invoke_middleware(request_id: str) -> Response:
    """Invoke correlation middleware without starting a server.

    Args:
        request_id: Caller correlation header value.

    Returns:
        In-memory downstream response after middleware.
    """

    async def call_next(request: Request) -> Response:
        """Return an honest unconfigured downstream response.

        Args:
            request: Request forwarded by middleware.

        Returns:
            Empty successful response.
        """

        del request
        return Response(status_code=200)

    from smart_rag_api.main import add_correlation_context

    return await add_correlation_context(_request(request_id), call_next)


def test_test_identity_bypass_requires_test_env_and_allow_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bypass is an AND of ``APP_ENV=test`` and ``ALLOW_TEST_IDENTITY``."""

    from smart_rag_api.dependencies.identity import test_identity_bypass_permitted
    from smart_rag_core.settings import load_backend_settings

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    assert test_identity_bypass_permitted(load_backend_settings()) is False

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "false")
    assert test_identity_bypass_permitted(load_backend_settings()) is False

    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    assert test_identity_bypass_permitted(load_backend_settings()) is True


def test_correlation_header_round_trips_without_claiming_readiness() -> None:
    """A safe caller request ID is returned while readiness stays unconfigured."""

    response = asyncio.run(_invoke_middleware("request-123"))

    from smart_rag_api.main import ready

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-123"
    assert ready()["status"] == "unconfigured"
    assert ready()["query_ready"] is False


def test_unsafe_correlation_header_is_replaced() -> None:
    """Control characters and oversized values never enter logging context."""

    response = asyncio.run(_invoke_middleware("unsafe value with spaces"))

    generated = response.headers["X-Request-ID"]
    assert generated != "unsafe value with spaces"
    assert re.fullmatch(r"[0-9a-f]{32}", generated)


def test_security_headers_are_present_on_live() -> None:
    """Security headers attach to JSON health responses."""

    test_client, create_app, as_openapi_client = _http_app()
    with test_client(create_app()) as raw:
        response = as_openapi_client(raw).get("/health/live")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "text/html" not in response.headers.get("content-type", "")


def test_local_openapi_docs_serve_html_with_docs_csp() -> None:
    """Local Swagger UI keeps ``text/html`` and a CDN-safe docs CSP."""

    test_client, create_app, as_openapi_client = _http_app()
    with test_client(create_app()) as raw:
        response = as_openapi_client(raw).get("/docs")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")
    csp = response.headers.get("content-security-policy", "")
    assert "cdn.jsdelivr.net" in csp
    assert "connect-src 'self'" in csp
    assert "swagger-ui" in response.text.lower()


def test_local_keeps_openapi_docs() -> None:
    """Local apps still mount ``/docs`` and ``/openapi.json``."""

    _, create_app, _as_openapi_client = _http_app()
    application = create_app()
    assert application.docs_url == "/docs"
    assert application.redoc_url == "/redoc"
    assert application.openapi_url == "/openapi.json"
    assert application.version == "0.1.0"


def test_staging_and_production_disable_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hosted apps do not mount unauthenticated OpenAPI or Swagger UI."""

    for app_env in ("staging", "production"):
        configure_hosted_backend_env(monkeypatch, app_env=app_env)
        test_client, create_app, as_openapi_client = _http_app()
        application = create_app()
        assert application.docs_url is None
        assert application.redoc_url is None
        assert application.openapi_url is None
        with test_client(application) as raw:
            client = as_openapi_client(raw)
            assert client.get("/docs").status_code == 404
            assert client.get("/redoc").status_code == 404
            assert client.get("/openapi.json").status_code == 404


def test_local_cors_omits_test_identity_headers() -> None:
    """Local CORS must not advertise ``X-Test-*`` identity headers."""

    test_client, create_app, as_openapi_client = _http_app()
    with test_client(create_app()) as raw:
        response = as_openapi_client(raw).get(
            "/health/live",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    allow = response.headers.get("access-control-allow-headers", "")
    assert "X-Test-" not in allow
    assert "Authorization" in allow
    assert "Idempotency-Key" in allow
    assert "X-Request-ID" in allow


def test_test_env_cors_advertises_test_identity_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``APP_ENV=test`` may list test identity headers for credentialed CORS."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "true")
    test_client, create_app, as_openapi_client = _http_app()
    with test_client(create_app()) as raw:
        response = as_openapi_client(raw).get(
            "/health/live",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
    allow = response.headers.get("access-control-allow-headers", "")
    assert "X-Test-User-Id" in allow
    assert "X-Test-AAL" in allow


def test_production_rejects_test_identity_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hosted apps return 400 when ``X-Test-*`` headers are present."""

    configure_hosted_backend_env(monkeypatch, app_env="production")
    test_client, create_app, as_openapi_client = _http_app()
    with test_client(create_app()) as raw:
        response = as_openapi_client(raw).get(
            "/health/live",
            headers={"X-Test-User-Id": "00000000-0000-4000-8000-000000000001"},
        )
    assert response.status_code == 400
    assert _json_object(response.json())["detail"] == "test_identity_forbidden"


def test_test_env_without_allow_flag_rejects_test_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``APP_ENV=test`` without ``ALLOW_TEST_IDENTITY`` cannot honor bypass."""

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_TEST_IDENTITY", "false")
    test_client, create_app, as_openapi_client = _http_app()
    with test_client(create_app()) as raw:
        response = as_openapi_client(raw).get(
            "/health/live",
            headers={"X-Test-Role": "owner"},
        )
    assert response.status_code == 400
    assert _json_object(response.json())["detail"] == "test_identity_forbidden"


def test_post_without_content_length_is_rejected() -> None:
    """Body methods fail closed when ``Content-Length`` is missing."""

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
        "method": "POST",
        "root_path": "",
        "path": "/conversations",
        "raw_path": b"/conversations",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "state": {},
    }
    request = Request(scope)

    async def call_next(_request: Request) -> Response:
        """Must not run when Content-Length is missing.

        Args:
            _request: Downstream request.

        Returns:
            A successful response that would indicate a skipped gate.
        """

        del _request
        return Response(status_code=200)

    response = asyncio.run(limit_request_body(request, call_next))
    assert response.status_code == 411
    assert (
        _json_object(json.loads(response.body))["detail"] == "content_length_required"
    )


def test_get_without_content_length_is_allowed() -> None:
    """SSE-safe methods without a body skip the Content-Length gate."""

    test_client, create_app, as_openapi_client = _http_app()
    with test_client(create_app()) as raw:
        response = as_openapi_client(raw).get("/health/live")
    assert response.status_code == 200
