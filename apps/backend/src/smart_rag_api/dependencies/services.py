"""Factory dependencies: routers receive services, never repositories."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from smart_rag_core.runtime.valkey import ValkeyClient
from smart_rag_core.settings import BackendSettings

from smart_rag_api.services.auth_rate_limits import RateLimitKind, check_auth_rate_limit


def get_backend_settings(request: Request) -> BackendSettings:
    """Return lifespan-validated backend settings.

    Args:
        request: Active request.

    Returns:
        Process settings.

    Raises:
        HTTPException: 503 when settings were not bound (import-only app).
    """

    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="settings_unconfigured",
        )
    return settings


def require_postgres_url(settings: BackendSettings) -> str:
    """Return the app_api Postgres URL or fail closed.

    Args:
        settings: Backend settings.

    Returns:
        Connection URL.

    Raises:
        HTTPException: 503 when unset.
    """

    if settings.supabase_db_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unconfigured",
        )
    return settings.supabase_db_url.get_secret_value()


def get_postgres_url(
    settings: Annotated[BackendSettings, Depends(get_backend_settings)],
) -> str:
    """FastAPI dependency wrapping ``require_postgres_url``.

    Args:
        settings: Injected settings.

    Returns:
        Postgres URL.
    """

    return require_postgres_url(settings)


def get_valkey_cache_client(request: Request) -> ValkeyClient | None:
    """Return the lifespan Valkey cache client when configured.

    Args:
        request: Active request.

    Returns:
        Cache client or None. Never the limits instance.
    """

    return getattr(request.app.state, "valkey_cache_client", None)


def get_valkey_limits_client(request: Request) -> ValkeyClient | None:
    """Return the lifespan Valkey limits client when configured.

    Args:
        request: Active request.

    Returns:
        Limits client or None.
    """

    return getattr(request.app.state, "valkey_limits_client", None)


def mark_rate_limit_degraded(request: Request) -> None:
    """Set the process degraded-readiness flag.

    Args:
        request: Active request.

    Side Effects:
        Sets ``app.state.rate_limit_degraded``.
    """

    request.app.state.rate_limit_degraded = True


def enforce_rate_limit(
    request: Request,
    *,
    bucket_key: str,
    kind: RateLimitKind,
    max_attempts: int,
    window_seconds: int = 60,
) -> None:
    """Apply FastAPI-owned rate limits and map failures to HTTP errors.

    Args:
        request: Active request with settings and optional Valkey client.
        bucket_key: Normalized bucket.
        kind: Endpoint class.
        max_attempts: Window cap.
        window_seconds: Window size.

    Raises:
        HTTPException: 429 with Retry-After, or 503 when enforcement is down.
    """

    settings: BackendSettings = get_backend_settings(request)
    try:
        check_auth_rate_limit(
            bucket_key=bucket_key,
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            postgres_url=settings.supabase_db_url,
            valkey_client=get_valkey_limits_client(request),
            kind=kind,
            on_degraded=lambda: mark_rate_limit_degraded(request),
            retry_after_seconds=settings.rate_limit_retry_after_seconds,
        )
    except Exception as exc:
        from smart_rag_api.services.auth_rate_limits import (
            AuthRateLimitExceededError,
            AuthRateLimitUnavailableError,
        )
        from smart_rag_api.services.http_errors import raise_limiter_http

        if isinstance(exc, (AuthRateLimitExceededError, AuthRateLimitUnavailableError)):
            raise_limiter_http(exc, retry_after=settings.rate_limit_retry_after_seconds)
        raise
