"""Burst-tolerant pre-auth IP limits for FastAPI-owned mutations.

Skips health and meta. OpenAPI and docs routes are not skipped; when local
docs stay enabled they are still subject to mutation-method limits. When
neither Valkey nor Postgres is configured the process is unconfigured (not a
dual outage) and this middleware does not fail-open a bound limiter — it
skips until backends exist. Dual outage of bound backends is fail-closed
inside ``check_auth_rate_limit``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from smart_rag_core.settings import BackendSettings

from smart_rag_api.services.auth_rate_limits import RateLimitKind, hashed_ip_bucket

_SKIP_PREFIXES = (
    "/health",
    "/api/meta",
)
_MUTATION_PREFIXES = (
    "/admin/",
    "/invitations/",
    "/conversations",
    "/documents/uploads",
    "/ingestion/crawls",
    "/ingestion/jobs/",
    "/runs/",
    "/tables/analyze",
    "/graph/",
)


def _is_mutation_path(path: str) -> bool:
    """Return whether ``path`` is a FastAPI-owned mutation.

    Args:
        path: Request path.

    Returns:
        True when pre-auth IP limits apply.
    """

    return any(path.startswith(prefix) for prefix in _MUTATION_PREFIXES)


async def limit_preauth_ip(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Apply hashed-IP burst limits to mutation methods.

    Args:
        request: Incoming request.
        call_next: Downstream continuation.

    Returns:
        Downstream response, or 429/503 from the limiter.
    """

    path = request.url.path
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return await call_next(request)
    if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return await call_next(request)
    if not _is_mutation_path(path):
        return await call_next(request)

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    valkey = getattr(request.app.state, "valkey_limits_client", None)
    postgres_configured = settings is not None and settings.supabase_db_url is not None
    if valkey is None and not postgres_configured:
        return await call_next(request)

    from smart_rag_api.dependencies.services import enforce_rate_limit

    client = request.client
    peer = client.host if client is not None else "unknown"
    enforce_rate_limit(
        request,
        bucket_key=hashed_ip_bucket(peer),
        kind=RateLimitKind.PRE_AUTH_IP,
        max_attempts=60,
    )
    return await call_next(request)
