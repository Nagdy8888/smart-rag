"""Security response headers for the FastAPI transport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Permitted-Cross-Domain-Policies": "none",
}

_DOCS_HTML_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})
_DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)


def _is_local_openapi_docs_route(path: str) -> bool:
    """Return whether ``path`` serves local-only Swagger/ReDoc HTML.

    Args:
        path: Request path from ASGI scope.

    Returns:
        True for mounted OpenAPI documentation HTML routes.
    """

    return path in _DOCS_HTML_PATHS


async def add_security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach explicit security headers. Never advertise HTML for JSON APIs.

    Args:
        request: Incoming HTTP request.
        call_next: Downstream ASGI continuation.

    Returns:
        Response with security headers set.
    """

    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if _is_local_openapi_docs_route(request.url.path):
        response.headers["Content-Security-Policy"] = _DOCS_CONTENT_SECURITY_POLICY
    media = response.headers.get("content-type", "")
    if media.startswith("text/event-stream"):
        return response
    if media.startswith("text/html") and not _is_local_openapi_docs_route(
        request.url.path
    ):
        response.headers["content-type"] = "application/json"
    return response
