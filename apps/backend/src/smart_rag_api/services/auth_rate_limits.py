"""FastAPI-owned rate limits with Valkey, Postgres fallback, and fail-closed mutations.

Browser-direct Supabase Auth (email/password, Google OAuth, password reset,
MFA enrollment/challenge) is never throttled here.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic

import psycopg
from pydantic import SecretStr
from smart_rag_core.runtime.valkey import (
    LIMITS_KEY_PREFIX,
    ValkeyClient,
    ValkeyTimeoutError,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_RETRY_AFTER_SECONDS = 60


class RateLimitKind(StrEnum):
    """Endpoint class that selects Valkey-loss policy."""

    AUTH_ADJACENT = "auth_adjacent"
    COST_MUTATION = "cost_mutation"
    LOW_RISK_READ = "low_risk_read"
    PRE_AUTH_IP = "pre_auth_ip"


class AuthRateLimitExceededError(Exception):
    """Raised when a sensitive operation exceeds its configured limit."""


class AuthRateLimitUnavailableError(Exception):
    """Raised when required limiter backends cannot enforce a mutation."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of one rate-limit check."""

    allowed: bool
    owner: str
    bucket_key: str
    degraded: bool = False
    retry_after_seconds: int = DEFAULT_RETRY_AFTER_SECONDS


class EmergencyLimiter:
    """Conservative per-process limiter for low-risk reads when Valkey is down."""

    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        """Create an empty windowed counter map.

        Args:
            max_attempts: Attempts allowed per window.
            window_seconds: Window size in seconds.
        """

        self._max = max_attempts
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, bucket_key: str) -> bool:
        """Return whether one attempt is allowed.

        Args:
            bucket_key: Prefixed bucket identifier.

        Returns:
            True when under the cap.
        """

        now = monotonic()
        with self._lock:
            stamps = [
                item for item in self._hits[bucket_key] if now - item < self._window
            ]
            if len(stamps) >= self._max:
                self._hits[bucket_key] = stamps
                return False
            stamps.append(now)
            self._hits[bucket_key] = stamps
            return True


_EMERGENCY = EmergencyLimiter(max_attempts=30, window_seconds=60)


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


def _postgres_consume(
    *,
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
    postgres_url: SecretStr,
) -> bool:
    """Open a short-lived connection and consume one Postgres bucket.

    Args:
        bucket_key: Normalized limit bucket.
        max_attempts: Cap.
        window_seconds: Window.
        postgres_url: Durable limiter URL.

    Returns:
        Whether the attempt is allowed.

    Raises:
        AuthRateLimitUnavailableError: On connection or SQL failure.
    """

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
    return allowed


def _valkey_consume(
    client: ValkeyClient,
    *,
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
) -> bool:
    """INCR a prefixed Valkey counter with a mandatory TTL.

    Args:
        client: Limits Valkey client.
        bucket_key: Application bucket.
        max_attempts: Cap.
        window_seconds: TTL/window.

    Returns:
        True when the new value is within the cap.

    Raises:
        ValkeyTimeoutError: On timeout or transport failure.
    """

    key = f"{LIMITS_KEY_PREFIX}{bucket_key}"
    value = client.incr(key, window_seconds)
    return value <= max_attempts


def hashed_ip_bucket(ip_address: str) -> str:
    """Return a log-safe pre-auth IP bucket key.

    Args:
        ip_address: Peer address. Never stored in audit as ``raw_ip``.

    Returns:
        ``preauth-ip:`` plus a truncated SHA-256 hex.
    """

    digest = hashlib.sha256(ip_address.encode("utf-8")).hexdigest()[:16]
    return f"preauth-ip:{digest}"


def check_auth_rate_limit(
    *,
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
    postgres_url: SecretStr | None,
    valkey_limits_url: SecretStr | None = None,
    valkey_client: ValkeyClient | None = None,
    kind: RateLimitKind = RateLimitKind.AUTH_ADJACENT,
    on_degraded: Callable[[], None] | None = None,
    on_recovered: Callable[[], None] | None = None,
    retry_after_seconds: int = DEFAULT_RETRY_AFTER_SECONDS,
) -> RateLimitDecision:
    """Enforce FastAPI-owned limits. Never claims to throttle hosted Auth.

    Policy:
        * ``auth_adjacent`` / ``cost_mutation`` / ``pre_auth_ip``: Valkey when
          available, then atomic Postgres; both failing returns 503. Mutations
          never skip the limiter (fail closed).
        * ``low_risk_read``: Valkey when available; on Valkey loss use the
          emergency process limiter, emit ``rate_limit_degraded``, and allow
          the conservative local cap. A later successful Valkey consume
          emits ``on_recovered`` so readiness can clear the latch.

    Args:
        bucket_key: Normalized limit bucket key.
        max_attempts: Allowed attempts per window.
        window_seconds: Window size in seconds.
        postgres_url: Durable degraded-limit database URL.
        valkey_limits_url: Unused when ``valkey_client`` is provided; retained
            for packet 1 call sites.
        valkey_client: Optional live/fake Valkey limits client.
        kind: Endpoint class selecting fail-closed vs emergency policy.
        on_degraded: Optional callback when the emergency limiter is used.
        on_recovered: Optional callback when Valkey consume succeeds again.
        retry_after_seconds: Hint returned on deny/unavailable.

    Returns:
        Decision describing whether the attempt is allowed.

    Raises:
        AuthRateLimitUnavailableError: When mutation enforcement stores fail.
        AuthRateLimitExceededError: When the attempt exceeds the configured cap.
    """

    del valkey_limits_url
    if valkey_client is not None:
        try:
            allowed = _valkey_consume(
                valkey_client,
                bucket_key=bucket_key,
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
            decision = RateLimitDecision(
                allowed=allowed,
                owner="fastapi_valkey",
                bucket_key=bucket_key,
                retry_after_seconds=retry_after_seconds,
            )
            if on_recovered is not None:
                on_recovered()
            if not allowed:
                raise AuthRateLimitExceededError(bucket_key)
            return decision
        except ValkeyTimeoutError:
            LOGGER.info(
                "valkey_limits_timeout",
                extra={"event": "auth_rate_limit.valkey.timeout", "kind": kind.value},
            )

    if kind is RateLimitKind.LOW_RISK_READ:
        allowed = _EMERGENCY.allow(bucket_key)
        if on_degraded is not None:
            on_degraded()
        LOGGER.warning(
            "rate_limit_degraded",
            extra={"event": "rate_limit_degraded", "kind": kind.value},
        )
        decision = RateLimitDecision(
            allowed=allowed,
            owner="fastapi_emergency",
            bucket_key=bucket_key,
            degraded=True,
            retry_after_seconds=retry_after_seconds,
        )
        if not allowed:
            raise AuthRateLimitExceededError(bucket_key)
        return decision

    if postgres_url is None:
        raise AuthRateLimitUnavailableError("postgres rate-limit backend unavailable")

    allowed = _postgres_consume(
        bucket_key=bucket_key,
        max_attempts=max_attempts,
        window_seconds=window_seconds,
        postgres_url=postgres_url,
    )
    decision = RateLimitDecision(
        allowed=allowed,
        owner="fastapi_postgres_degraded",
        bucket_key=bucket_key,
        retry_after_seconds=retry_after_seconds,
    )
    if not allowed:
        raise AuthRateLimitExceededError(bucket_key)
    return decision
