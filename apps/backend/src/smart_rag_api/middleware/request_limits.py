"""Request body size gate. Oversized payloads fail closed with HTTP 413."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from smart_rag_core.settings import BackendSettings
from starlette.types import Message, Receive

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
_SAFE_NO_BODY_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})


class _BodyLimitExceeded(Exception):
    """Raised when the wrapped ASGI receive exceeds ``request_max_body_bytes``."""


def _content_length_is_numeric(raw_length: str | None) -> bool:
    """Return whether ``Content-Length`` is a non-negative integer string.

    Args:
        raw_length: Raw ``Content-Length`` header, if present.

    Returns:
        True when the value is entirely digits.
    """

    return raw_length is not None and raw_length.isdigit()


def _install_receive_byte_limit(request: Request, maximum: int) -> None:
    """Wrap ``receive`` so streamed bodies cannot exceed ``maximum`` bytes.

    Args:
        request: Incoming request whose ASGI receive will be wrapped.
        maximum: Inclusive maximum body size in bytes.

    Side Effects:
        Replaces ``request._receive``. Downstream body reads observe the cap.
        SSE GET requests must not call this helper when they have no body.
    """

    original_receive: Receive = request.receive
    received = 0

    async def limited_receive() -> Message:
        """Count request-body bytes and fail closed past the cap.

        Returns:
            The next ASGI message.

        Raises:
            _BodyLimitExceeded: When accumulated body bytes exceed ``maximum``.
        """

        nonlocal received
        message = await original_receive()
        if message["type"] == "http.request":
            chunk = message.get("body", b"")
            if isinstance(chunk, (bytes, bytearray)):
                received += len(chunk)
            elif isinstance(chunk, memoryview):
                received += chunk.nbytes
            if received > maximum:
                raise _BodyLimitExceeded()
        return message

    request._receive = limited_receive  # pyright: ignore[reportPrivateUsage]


def _payload_too_large() -> JSONResponse:
    """Return the canonical oversized-body JSON response.

    Returns:
        HTTP 413 with ``payload_too_large``.
    """

    return JSONResponse(status_code=413, content={"detail": "payload_too_large"})


def _content_length_required() -> JSONResponse:
    """Return the fail-closed missing-length JSON response.

    Returns:
        HTTP 411 with ``content_length_required``.
    """

    return JSONResponse(
        status_code=411,
        content={"detail": "content_length_required"},
    )


async def limit_request_body(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Reject bodies larger than ``request_max_body_bytes``.

    POST, PUT, and PATCH require a numeric ``Content-Length`` and fail closed
    when it is missing or non-numeric. GET, HEAD, OPTIONS, and DELETE without
    a body skip the gate so SSE resume stays intact. A wrapped ``receive``
    counts bytes up to the cap when a body is expected.

    Args:
        request: Incoming HTTP request.
        call_next: Downstream continuation.

    Returns:
        411 JSON when a body method omits ``Content-Length``, 413 JSON when
        the declared or streamed size exceeds the cap, otherwise the
        downstream response.
    """

    application = request.scope.get("app")
    settings: BackendSettings | None = getattr(
        getattr(application, "state", None),
        "settings",
        None,
    )
    maximum = 1_048_576 if settings is None else settings.request_max_body_bytes
    method = request.method.upper()
    raw_length = request.headers.get("content-length")
    numeric = _content_length_is_numeric(raw_length)
    declared = int(raw_length) if numeric and raw_length is not None else 0

    if method in _BODY_METHODS:
        if not numeric:
            return _content_length_required()
        if declared > maximum:
            return _payload_too_large()
        _install_receive_byte_limit(request, maximum)
        try:
            return await call_next(request)
        except _BodyLimitExceeded:
            return _payload_too_large()

    if method in _SAFE_NO_BODY_METHODS:
        if numeric and declared > 0:
            if declared > maximum:
                return _payload_too_large()
            _install_receive_byte_limit(request, maximum)
            try:
                return await call_next(request)
            except _BodyLimitExceeded:
                return _payload_too_large()
        return await call_next(request)

    if numeric and declared > maximum:
        return _payload_too_large()
    return await call_next(request)
