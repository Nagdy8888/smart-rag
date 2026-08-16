"""Exact-origin CORS. Wildcard origins never pair with credentials."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from smart_rag_core.settings import BackendSettings
from starlette.responses import Response as StarletteResponse

_DEFAULT_ORIGINS = ("http://127.0.0.1:3000", "http://localhost:3000")
_ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
_ALLOW_HEADERS = (
    "Authorization, Content-Type, Idempotency-Key, Last-Event-ID, "
    "X-Client-Version, X-Request-ID, "
    "X-Test-User-Id, X-Test-Role, X-Test-Authorization-Version, X-Test-Email"
)
_EXPOSE_HEADERS = "X-Request-ID, Retry-After"


def _allowed_origins(request: Request) -> tuple[str, ...]:
    """Return exact CORS origins from settings or local defaults.

    Args:
        request: Active request.

    Returns:
        Exact origin strings. Never ``*``.
    """

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    if settings is None:
        return _DEFAULT_ORIGINS
    return settings.parsed_cors_origins()


async def add_cors(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Reflect an exact allowed Origin. Never send ``*`` with credentials.

    Args:
        request: Incoming request.
        call_next: Downstream continuation.

    Returns:
        Response with CORS headers when the Origin is allow-listed.
    """

    origin = request.headers.get("origin")
    allowed = _allowed_origins(request)
    if request.method == "OPTIONS" and origin is not None and origin in allowed:
        preflight = StarletteResponse(status_code=204)
        _apply_cors(preflight, origin)
        return preflight
    response = await call_next(request)
    if origin is not None and origin in allowed:
        _apply_cors(response, origin)
    return response


def _apply_cors(response: Response, origin: str) -> None:
    """Set credentialed CORS headers for one exact origin.

    Args:
        response: Outgoing response.
        origin: Allow-listed Origin value.
    """

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = _ALLOW_METHODS
    response.headers["Access-Control-Allow-Headers"] = _ALLOW_HEADERS
    response.headers["Access-Control-Expose-Headers"] = _EXPOSE_HEADERS
    response.headers["Access-Control-Max-Age"] = "600"
    response.headers["Vary"] = "Origin"
