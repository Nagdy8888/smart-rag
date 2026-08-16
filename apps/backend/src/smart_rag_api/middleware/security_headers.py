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
    media = response.headers.get("content-type", "")
    if media.startswith("text/event-stream"):
        return response
    if media.startswith("text/html"):
        response.headers["content-type"] = "application/json"
    return response
