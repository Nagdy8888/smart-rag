"""Exact-origin CORS. Wildcard origins never pair with credentials."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from smart_rag_core.settings import BackendSettings, Environment
from starlette.responses import Response as StarletteResponse

_DEFAULT_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3010",
    "http://localhost:3010",
)
_ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
_PRODUCTION_ALLOW_HEADERS = (
    "Authorization, Content-Type, Idempotency-Key, Last-Event-ID, "
    "X-Client-Version, X-Request-ID"
)
_TEST_ALLOW_HEADERS = (
    f"{_PRODUCTION_ALLOW_HEADERS}, "
    "X-Test-User-Id, X-Test-Role, X-Test-Authorization-Version, "
    "X-Test-Email, X-Test-AAL"
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


def _allow_headers(request: Request) -> str:
    """Return credentialed Allow-Headers for the active environment.

    Test identity headers are advertised only when ``APP_ENV=test``.

    Args:
        request: Active request.

    Returns:
        Comma-separated header names. Never includes ``X-Test-*`` outside
        the test environment.
    """

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    if settings is not None and settings.app_env is Environment.TEST:
        return _TEST_ALLOW_HEADERS
    return _PRODUCTION_ALLOW_HEADERS


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
        _apply_cors(preflight, origin, request)
        return preflight
    response = await call_next(request)
    if origin is not None and origin in allowed:
        _apply_cors(response, origin, request)
    return response


def _apply_cors(response: Response, origin: str, request: Request) -> None:
    """Set credentialed CORS headers for one exact origin.

    When the browser asks for private-network access, the response allows
    it. That header is what lets a public HTTPS page call this API on
    ``127.0.0.1``.

    Args:
        response: Outgoing response.
        origin: Allow-listed Origin value.
        request: Active request used to choose Allow-Headers.
    """

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = _ALLOW_METHODS
    response.headers["Access-Control-Allow-Headers"] = _allow_headers(request)
    response.headers["Access-Control-Expose-Headers"] = _EXPOSE_HEADERS
    response.headers["Access-Control-Max-Age"] = "600"
    response.headers["Vary"] = "Origin"
    # A public HTTPS page calling this loopback listener (the Vercel console
    # on the same laptop) sends a private-network preflight. Reflect it only
    # for an origin that is already allow-listed.
    if request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Vary"] = "Origin, Access-Control-Request-Private-Network"
