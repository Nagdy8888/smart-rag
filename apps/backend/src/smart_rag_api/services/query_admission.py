"""Thin FastAPI admission service: rate/concurrency-before-cost, then core RPC.

Packet 5 owns public chat/SSE routers and provider-versus-FastAPI Auth rate
ownership. This module is not a streaming endpoint.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg
from pydantic import SecretStr
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import (
    QueryAdmissionResult,
    admit_query_run,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext

from smart_rag_api.services.auth_rate_limits import (
    AuthRateLimitExceededError,
    AuthRateLimitUnavailableError,
    check_auth_rate_limit,
)

QUERY_ADMISSION_RATE_MAX_ATTEMPTS = 20
"""Phase 6 packet 1 engineering default. Packet 5 owns the signed policy."""

QUERY_ADMISSION_RATE_WINDOW_SECONDS = 60
QUERY_ADMISSION_BUCKET_PREFIX = "query-admission"


def query_admission_bucket_key(user_id: str) -> str:
    """Return the FastAPI-owned Postgres rate-limit bucket for one user.

    Args:
        user_id: Server-derived subject UUID string.

    Returns:
        Bucket key including the user id. Valkey is not authoritative.
    """

    return f"{QUERY_ADMISSION_BUCKET_PREFIX}:{user_id}"


def admit_query_run_for_caller(
    postgres_url: str,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    idempotency_key: UUID,
    message: str,
    route_family: Phase6RouteFamily,
    token_issued_at: datetime | None = None,
    postgres_rate_limit_url: SecretStr | None = None,
    valkey_limits_url: SecretStr | None = None,
) -> QueryAdmissionResult:
    """Apply FastAPI rate limits, then admit through the durable RPC.

    Rate-limit and limiter-unavailable failures do not insert a reservation.
    Concurrency is the durable five-run SQL cap, not Valkey. Client role,
    client USD, cache, BM25, and graph output are not consulted.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller: JWKS-verified, profile-reloaded identity.
        conversation_id: Conversation the caller must own.
        idempotency_key: Client-generated UUID message key.
        message: User message text hashed into the payload.
        route_family: Server-selected family for the ceiling table.
        token_issued_at: JWT ``iat`` for profile-wide revocation.
        postgres_rate_limit_url: Degraded limiter URL. Defaults to
            ``postgres_url``. Missing backends fail closed.
        valkey_limits_url: Optional unused fast path. Never authorizes spend.

    Returns:
        Authorized runtime context from the durable admit RPC.

    Raises:
        QueryAdmissionError: ``rate_limited`` / ``limiter_unavailable`` before
            cost, or RPC admission failures after the limiter allows.

    Side Effects:
        Consumes one Postgres rate-limit attempt. On success, inserts or
        reconnects one query run and reservation.
    """

    limiter_url = postgres_rate_limit_url or SecretStr(postgres_url)
    try:
        check_auth_rate_limit(
            bucket_key=query_admission_bucket_key(caller.user_id),
            max_attempts=QUERY_ADMISSION_RATE_MAX_ATTEMPTS,
            window_seconds=QUERY_ADMISSION_RATE_WINDOW_SECONDS,
            postgres_url=limiter_url,
            valkey_limits_url=valkey_limits_url,
        )
    except AuthRateLimitExceededError as exc:
        raise QueryAdmissionError("rate_limited") from exc
    except AuthRateLimitUnavailableError as exc:
        raise QueryAdmissionError("limiter_unavailable") from exc

    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=route_family,
        message=message,
    )
    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            result = admit_query_run(
                connection,
                caller=caller,
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                route_family=route_family,
                token_issued_at=token_issued_at,
            )
            connection.commit()
    except QueryAdmissionError:
        raise
    except psycopg.Error as exc:
        raise QueryAdmissionError("database_rejected") from exc
    return result
