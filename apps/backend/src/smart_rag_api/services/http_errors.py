"""Map limiter and admission errors to sanitized HTTPExceptions."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.services.auth_rate_limits import (
    DEFAULT_RETRY_AFTER_SECONDS,
    AuthRateLimitExceededError,
    AuthRateLimitUnavailableError,
)

_ADMISSION_STATUS: dict[str, int] = {
    "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "limiter_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "authorization_rejected": status.HTTP_403_FORBIDDEN,
    "not_found": status.HTTP_404_NOT_FOUND,
    "run_forbidden": status.HTTP_404_NOT_FOUND,
    "conversation_deleted": status.HTTP_404_NOT_FOUND,
    "conversation_forbidden": status.HTTP_404_NOT_FOUND,
    "idempotency_conflict": status.HTTP_409_CONFLICT,
    "budget_exhausted": status.HTTP_402_PAYMENT_REQUIRED,
    "concurrency_limit": status.HTTP_429_TOO_MANY_REQUESTS,
    "run_not_cancellable": status.HTTP_409_CONFLICT,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "invalid_rating": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_tag": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "tag_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_query": status.HTTP_400_BAD_REQUEST,
    "invalid_key": status.HTTP_400_BAD_REQUEST,
    "invalid_cursor": status.HTTP_400_BAD_REQUEST,
    "database_rejected": status.HTTP_503_SERVICE_UNAVAILABLE,
    "conversation_create_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def raise_limiter_http(
    exc: AuthRateLimitExceededError | AuthRateLimitUnavailableError,
    *,
    retry_after: int = DEFAULT_RETRY_AFTER_SECONDS,
) -> NoReturn:
    """Raise 429 or 503 with Retry-After.

    Args:
        exc: Limiter failure.
        retry_after: Seconds advertised to the client.

    Raises:
        HTTPException: Always.
    """

    if isinstance(exc, AuthRateLimitExceededError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limited",
            headers={"Retry-After": str(retry_after)},
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="limiter_unavailable",
        headers={"Retry-After": str(retry_after)},
    ) from exc


def raise_admission_http(exc: QueryAdmissionError) -> NoReturn:
    """Map durable admission reasons to sanitized HTTP errors.

    Args:
        exc: Admission or conversation/run RPC failure.

    Raises:
        HTTPException: Always.
    """

    code = _ADMISSION_STATUS.get(exc.reason, status.HTTP_400_BAD_REQUEST)
    headers = None
    if code in {
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    }:
        headers = {"Retry-After": str(DEFAULT_RETRY_AFTER_SECONDS)}
    detail = exc.reason if exc.reason in _ADMISSION_STATUS else "request_rejected"
    if code == status.HTTP_404_NOT_FOUND:
        detail = "not_found"
    raise HTTPException(status_code=code, detail=detail, headers=headers) from exc
