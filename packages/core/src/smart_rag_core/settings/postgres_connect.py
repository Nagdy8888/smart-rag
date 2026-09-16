"""Psycopg connections that stay safe on hosted transaction poolers."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import psycopg

LOGGER = logging.getLogger(__name__)

TRANSIENT_CONNECT_REASON = "transient_connect"
MAX_RETRY_DELAY_SECONDS = 0.1
DEFAULT_CONNECT_ATTEMPTS = 2
DEFAULT_RETRY_BUDGET_SECONDS = 1.0


def sqlstate_of(exc: BaseException) -> str | None:
    """Return the first Postgres SQLSTATE on ``exc`` or its cause chain.

    Args:
        exc: Driver or wrapped network error.

    Returns:
        Five-character SQLSTATE, or None when the chain has none.
    """

    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 6:
        sqlstate = getattr(current, "sqlstate", None)
        if isinstance(sqlstate, str) and len(sqlstate) == 5:
            return sqlstate
        current = current.__cause__ or current.__context__
        seen += 1
    return None


def is_transient_connect_failure(exc: BaseException) -> bool:
    """Return whether ``exc`` is a retryable connect/transport failure.

    Retries only SQLSTATE class ``08`` or a socket/DNS/connect wrapper with
    no SQLSTATE. Authentication, syntax, and integrity errors are not
    retryable.

    Args:
        exc: Driver, OS, or wrapped failure.

    Returns:
        True when one additional connect attempt is allowed.
    """

    sqlstate = sqlstate_of(exc)
    if sqlstate is not None:
        return sqlstate.startswith("08")
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 6:
        if isinstance(current, OSError):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


def connect_postgres(
    conninfo: str,
    *,
    max_attempts: int = DEFAULT_CONNECT_ATTEMPTS,
    retry_budget_seconds: float = DEFAULT_RETRY_BUDGET_SECONDS,
    monotonic_clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> psycopg.Connection:
    """Open Postgres with automatic prepared statements disabled.

    Hosted Supabase transaction poolers (port 6543 / Supavisor) reuse backend
    sessions across clients. Psycopg 3's default named prepares then raise
    ``DuplicatePreparedStatement`` on the next checkout. SSE event-store and
    LangGraph checkpointer already disable prepares; query retrieve and persist
    must do the same.

    At most ``max_attempts`` connects run inside ``retry_budget_seconds``.
    The second attempt waits at most 100 ms and never longer than remaining
    budget. Logs include only operation, attempt, and a fixed reason code.

    Args:
        conninfo: Postgres DSN. Callers must not log this value.
        max_attempts: Inclusive connect attempts. Default 2.
        retry_budget_seconds: Wall-clock budget for retries. Default 1.0.
        monotonic_clock: Injected clock for tests.
        sleep: Injected sleeper for tests.
        **kwargs: Extra ``psycopg.connect`` keyword arguments. Callers may
            override ``prepare_threshold`` only in tests that need it.

    Returns:
        An open connection.

    Raises:
        psycopg.Error: Connection or authentication failure after retries.
        OSError: Network failure before the driver wraps it.
    """

    kwargs.setdefault("prepare_threshold", None)
    started = monotonic_clock()
    attempts = max(1, max_attempts)
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return psycopg.connect(conninfo, **kwargs)
        except Exception as exc:
            last_error = exc
            remaining = retry_budget_seconds - (monotonic_clock() - started)
            if (
                attempt >= attempts
                or remaining <= 0
                or not is_transient_connect_failure(exc)
            ):
                raise
            delay = min(MAX_RETRY_DELAY_SECONDS, remaining)
            LOGGER.info(
                "postgres connect retry",
                extra={
                    "operation": "connect_postgres",
                    "attempt": attempt,
                    "reason": TRANSIENT_CONNECT_REASON,
                },
            )
            sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("connect_postgres exhausted attempts")
