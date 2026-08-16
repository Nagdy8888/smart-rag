"""Durable LangSmith deletion *requests* with retry inside a 24h SLA."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class LangSmithDeletionTransport(Protocol):
    """HTTP transport for one deletion request. Never claims cloud success."""

    def request_delete(self, hashed_trace_keys: Sequence[str]) -> None:
        """Send one deletion request.

        Args:
            hashed_trace_keys: Hashed run/trace identifiers only.

        Raises:
            RuntimeError: When the HTTP request fails and should retry.
        """


@dataclass(frozen=True, slots=True)
class LangSmithDeletionClaim:
    """One claimed deletion request row.

    Attributes:
        request_id: Primary key.
        hashed_trace_keys: Hashed run ids / trace keys.
        status: Durable status after claim.
        attempts: Attempt count including this claim.
        sla_deadline_at: 24h SLA instant.
    """

    request_id: UUID
    hashed_trace_keys: tuple[str, ...]
    status: str
    attempts: int
    sla_deadline_at: datetime


class RecordingLangSmithDeletionTransport:
    """Test transport that records hashed keys and never opens a socket."""

    def __init__(self, *, fail_times: int = 0) -> None:
        """Create a recorder.

        Args:
            fail_times: Number of initial calls that raise before succeeding.
        """

        self.calls: list[tuple[str, ...]] = []
        self._fail_times = fail_times

    def request_delete(self, hashed_trace_keys: Sequence[str]) -> None:
        """Record hashed keys. Raise until ``fail_times`` is exhausted.

        Args:
            hashed_trace_keys: Hashed identifiers.

        Raises:
            RuntimeError: While remaining configured failures exist.
        """

        self.calls.append(tuple(hashed_trace_keys))
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("langsmith_delete_request_failed")


def claim_langsmith_deletion_requests(
    connection: psycopg.Connection,
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> tuple[LangSmithDeletionClaim, ...]:
    """Claim due deletion request rows.

    Args:
        connection: Open worker connection.
        now: Injected clock.
        limit: Maximum rows.

    Returns:
        Claimed rows, including those already marked ``sla_expired``.
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        if now is None:
            cursor.execute(
                "SELECT * FROM app.claim_langsmith_deletion_requests(timezone('utc', now()), %s)",
                (limit,),
            )
        else:
            cursor.execute(
                "SELECT * FROM app.claim_langsmith_deletion_requests(%s, %s)",
                (now, limit),
            )
        rows = cursor.fetchall()
    claims: list[LangSmithDeletionClaim] = []
    for row in rows:
        hashed_obj: object = row["hashed_trace_keys"]
        keys: list[str] = []
        if isinstance(hashed_obj, list):
            for item in cast(list[object], hashed_obj):
                keys.append(str(item))
        deadline = row["sla_deadline_at"]
        if not isinstance(deadline, datetime):
            raise TypeError("langsmith_sla_deadline_type")
        claims.append(
            LangSmithDeletionClaim(
                request_id=UUID(str(row["id"])),
                hashed_trace_keys=tuple(keys),
                status=str(row["status"]),
                attempts=int(row["attempts"]),
                sla_deadline_at=deadline,
            )
        )
    return tuple(claims)


def record_langsmith_deletion_attempt(
    connection: psycopg.Connection,
    *,
    request_id: UUID,
    success: bool,
    error: str | None = None,
    now: datetime | None = None,
) -> None:
    """Persist one HTTP attempt outcome.

    Args:
        connection: Open worker connection.
        request_id: Claimed row.
        success: True when the deletion *request* was accepted by HTTP.
        error: Sanitized error, never a payload body.
        now: Injected clock.

    Side Effects:
        Updates ``app.langsmith_deletion_requests``.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.record_langsmith_deletion_attempt(%s, %s, %s, %s)
            """,
            (
                request_id,
                success,
                error,
                now,
            ),
        )


def process_langsmith_deletion_requests(
    connection: psycopg.Connection,
    *,
    transport: LangSmithDeletionTransport,
    now: datetime | None = None,
    limit: int = 20,
    on_sla_expired: Callable[[LangSmithDeletionClaim], None] | None = None,
) -> tuple[int, int, int]:
    """Claim due rows, send deletion requests, and record outcomes.

    Args:
        connection: Open worker connection.
        transport: HTTP or test transport.
        now: Injected clock.
        limit: Maximum rows per cycle.
        on_sla_expired: Optional hook when the 24h SLA is recorded.

    Returns:
        ``(recorded, retried, sla_expired)`` counts. Does not claim that
        LangSmith deleted cloud traces.

    Side Effects:
        Updates durable request rows. May call ``transport.request_delete``.
    """

    recorded = 0
    retried = 0
    sla_expired = 0
    for claim in claim_langsmith_deletion_requests(connection, now=now, limit=limit):
        if claim.status == "sla_expired":
            sla_expired += 1
            if on_sla_expired is not None:
                on_sla_expired(claim)
            continue
        try:
            transport.request_delete(claim.hashed_trace_keys)
        except Exception as exc:
            record_langsmith_deletion_attempt(
                connection,
                request_id=claim.request_id,
                success=False,
                error=type(exc).__name__,
                now=now,
            )
            retried += 1
            continue
        record_langsmith_deletion_attempt(
            connection,
            request_id=claim.request_id,
            success=True,
            now=now,
        )
        recorded += 1
    return recorded, retried, sla_expired


class HttpLangSmithDeletionTransport:
    """POST hashed trace keys to LangSmith. Never claims cloud deletion."""

    def __init__(
        self,
        *,
        api_key: str | None,
        endpoint: str = "https://api.smith.langchain.com",
    ) -> None:
        """Create an HTTP transport.

        Args:
            api_key: LangSmith API key. Missing keys fail closed for retry.
            endpoint: LangSmith API origin.
        """

        self._api_key = api_key
        self._endpoint = endpoint.rstrip("/")

    def request_delete(self, hashed_trace_keys: Sequence[str]) -> None:
        """Send one deletion *request* containing hashed keys only.

        Args:
            hashed_trace_keys: Hashed run/trace identifiers.

        Raises:
            RuntimeError: When the API key is missing or HTTP fails
                (except 404, which still records that a request was sent).

        Side Effects:
            One HTTPS POST. Response bodies are not logged.
        """

        if not self._api_key:
            raise RuntimeError("langsmith_api_key_missing")
        if not self._endpoint.startswith("https://"):
            raise RuntimeError("langsmith_endpoint_not_https")
        payload = json.dumps({"hashed_trace_keys": list(hashed_trace_keys)}).encode(
            "utf-8"
        )
        request = urllib.request.Request(  # noqa: S310
            f"{self._endpoint}/api/v1/runs/delete",
            data=payload,
            method="POST",
            headers={
                "x-api-key": self._api_key,
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                status = int(getattr(response, "status", 200))
                if status >= 400 and status != 404:
                    raise RuntimeError(f"langsmith_http_{status}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return
            raise RuntimeError(f"langsmith_http_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("langsmith_request_failed") from exc
