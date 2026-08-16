"""Request body size gate. Oversized payloads fail closed with HTTP 413."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from smart_rag_core.settings import BackendSettings


async def limit_request_body(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Reject bodies larger than ``request_max_body_bytes``.

    Args:
        request: Incoming HTTP request.
        call_next: Downstream continuation.

    Returns:
        413 JSON when ``Content-Length`` exceeds the configured cap, otherwise
        the downstream response.
    """

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    maximum = 1_048_576 if settings is None else settings.request_max_body_bytes
    raw_length = request.headers.get("content-length")
    if raw_length is not None and raw_length.isdigit() and int(raw_length) > maximum:
        return JSONResponse(
            status_code=413,
            content={"detail": "payload_too_large"},
        )
    return await call_next(request)
