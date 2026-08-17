"""Unit tests for backend correlation middleware and honest readiness."""

from __future__ import annotations

import asyncio
import re

from fastapi import Request, Response
from smart_rag_api.main import add_correlation_context, ready
from starlette.types import Scope


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

    return await add_correlation_context(_request(request_id), call_next)


def test_correlation_header_round_trips_without_claiming_readiness() -> None:
    """A safe caller request ID is returned while readiness stays unconfigured."""

    response = asyncio.run(_invoke_middleware("request-123"))

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

    from fastapi.testclient import TestClient
    from smart_rag_api.main import create_app

    from tests.unit.typed_openapi import as_openapi_client

    with TestClient(create_app()) as raw:
        response = as_openapi_client(raw).get("/health/live")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "text/html" not in response.headers.get("content-type", "")
