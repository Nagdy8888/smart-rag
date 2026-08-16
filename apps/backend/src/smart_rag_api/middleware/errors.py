"""Generic sanitized HTTP errors. Internals never leak to clients."""

from __future__ import annotations

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ExceptionHandler

LOGGER = logging.getLogger(__name__)


def _detail_text(detail: object) -> str:
    """Return a JSON-safe detail string.

    Args:
        detail: HTTPException.detail, which FastAPI types as ``str``.

    Returns:
        Sanitized detail token.
    """

    if type(detail) is str and detail:
        return detail
    return "request_rejected"


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Return a JSON body for HTTPException.

    Args:
        request: Active request.
        exc: HTTP error.

    Returns:
        JSON response with a sanitized ``detail`` string.
    """

    del request
    headers = dict(exc.headers) if exc.headers is not None else None
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": _detail_text(exc.detail)},
        headers=headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Fail closed on schema validation without echoing raw HTML.

    Args:
        request: Active request.
        exc: Pydantic/FastAPI validation error.

    Returns:
        HTTP 422 with generic validation detail.
    """

    del request, exc
    return JSONResponse(
        status_code=422,
        content={"detail": "validation_failed"},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Hide unexpected exceptions behind a generic 500.

    Args:
        request: Active request.
        exc: Unhandled error.

    Returns:
        HTTP 500 JSON.

    Side Effects:
        Logs the exception class only, not request bodies or source text.
    """

    del request
    LOGGER.exception(
        "unhandled_error",
        extra={"event": "http.unhandled", "error_type": type(exc).__name__},
    )
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


def install_error_handlers(application: FastAPI) -> None:
    """Register fail-closed handlers that return JSON, never HTML.

    Args:
        application: FastAPI app.
    """

    application.add_exception_handler(
        StarletteHTTPException,
        cast(ExceptionHandler, http_exception_handler),
    )
    application.add_exception_handler(
        RequestValidationError,
        cast(ExceptionHandler, validation_exception_handler),
    )
    application.add_exception_handler(
        Exception,
        cast(ExceptionHandler, unhandled_exception_handler),
    )
