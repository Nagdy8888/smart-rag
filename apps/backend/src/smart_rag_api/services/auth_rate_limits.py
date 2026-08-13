"""FastAPI-owned auth-adjacent rate limits with Postgres degraded fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import psycopg
from pydantic import SecretStr

LOGGER = logging.getLogger(__name__)


class AuthRateLimitExceededError(Exception):
    """Raised when a sensitive operation exceeds its configured limit."""


class AuthRateLimitUnavailableError(Exception):
    """Raised when neither Valkey nor Postgres degraded limits are reachable."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of one rate-limit check."""

    allowed: bool
    owner: str
    bucket_key: str


def consume_postgres_auth_rate_limit(
    connection: psycopg.Connection,
    *,
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
) -> bool:
    """Consume one attempt through ``private.consume_auth_rate_limit``.

    Args:
        connection: Open Postgres connection with ``app_api`` privileges.
        bucket_key: Stable bucket identifier (already normalized by caller).
        max_attempts: Maximum attempts allowed in the window.
        window_seconds: Fixed window size in seconds.

    Returns:
        ``True`` when the attempt is allowed; ``False`` when exhausted.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT private.consume_auth_rate_limit(%s, %s, %s)
            """,
            (bucket_key, max_attempts, window_seconds),
        )
        row = cursor.fetchone()
    if row is None:
        return False
    return bool(row[0])


def check_auth_rate_limit(
    *,
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
    postgres_url: SecretStr | None,
    valkey_limits_url: SecretStr | None = None,
) -> RateLimitDecision:
    """Apply degraded Postgres limits; Valkey fast path optional.

    Args:
        bucket_key: Normalized limit bucket key.
        max_attempts: Allowed attempts per window.
        window_seconds: Window size in seconds.
        postgres_url: Durable degraded-limit database URL.
        valkey_limits_url: Optional Valkey URL for a future fast path.

    Returns:
        Decision describing whether the attempt is allowed.

    Raises:
        AuthRateLimitUnavailableError: When Postgres is unreachable and Valkey
            is not configured.
        AuthRateLimitExceededError: When the attempt exceeds the configured cap.
    """

    if valkey_limits_url is not None:
        LOGGER.debug(
            "Valkey auth rate-limit fast path not wired; using Postgres fallback",
            extra={"event": "auth_rate_limit.valkey.deferred", "bucket": bucket_key},
        )

    if postgres_url is None:
        raise AuthRateLimitUnavailableError("postgres rate-limit backend unavailable")

    try:
        with psycopg.connect(postgres_url.get_secret_value()) as connection:
            connection.execute("SET ROLE app_api")
            allowed = consume_postgres_auth_rate_limit(
                connection,
                bucket_key=bucket_key,
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
            connection.commit()
    except psycopg.Error as exc:
        raise AuthRateLimitUnavailableError(
            "postgres rate-limit backend error"
        ) from exc

    decision = RateLimitDecision(
        allowed=allowed,
        owner="fastapi_postgres_degraded",
        bucket_key=bucket_key,
    )
    if not allowed:
        raise AuthRateLimitExceededError(bucket_key)
    return decision
