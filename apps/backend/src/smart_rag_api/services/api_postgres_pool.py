"""Process-local app_api connection pools for admit and graph-open.

Each new client connection to the hosted transaction pooler pays a TLS
handshake of about 500 ms. These pools keep a few of those connections
idle so the next Ask reuses them. They sit inside the FastAPI
request/RPC cap of 10 documented in
``docs/architecture/05-database-connections.md``: the event store already
reserves 4, admission reserves 2, and a live run reserves 4. A checkout
that finds every slot lent opens one ordinary connection and closes it
when finished, which is the same ephemeral connect this path used before
pooling.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import cast

import psycopg
from psycopg.pq import TransactionStatus
from smart_rag_core.settings.postgres_connect import connect_postgres
from smart_rag_core.settings.postgres_pool import BoundedConnectionPool, PoolBusyError

LOGGER = logging.getLogger(__name__)

APP_API_TRANSACTION_ROLE_SQL = "SET LOCAL ROLE app_api"
"""Role for one transaction. ``SET LOCAL`` ends at commit, so a pooled
session does not keep ``app_api`` for the next borrower."""

ADMISSION_POOL_MAX_SIZE = 2
"""Most concurrent admit transactions. Released before the graph starts."""

RUN_POOL_MAX_SIZE = 4
"""Most graph connections kept warm. A fifth concurrent run connects directly."""

API_POOL_WAIT_SECONDS = 0.05
"""How long a checkout waits for a warm session before opening a new one.

Waiting out a busy pool would add latency. A fresh connect is the previous
behavior, so the wait stays short."""

API_POOL_IDLE_SECONDS = 60.0
"""Idle sessions older than this are closed instead of reused."""

_LOCK = Lock()
_ADMISSION_POOLS: dict[str, BoundedConnectionPool] = {}
_RUN_POOLS: dict[str, BoundedConnectionPool] = {}


@dataclass
class _Checkout:
    """One lent connection and the pool that must take it back."""

    pool: BoundedConnectionPool
    pooled: bool


_CHECKOUTS: dict[int, _Checkout] = {}


def close_api_postgres_pools() -> None:
    """Close idle pooled sessions. Lent ones close when they are released.

    Side Effects:
        Drops process pools so the next checkout connects again. Safe to
        call more than once.
    """
    with _LOCK:
        pools = [*_ADMISSION_POOLS.values(), *_RUN_POOLS.values()]
        _ADMISSION_POOLS.clear()
        _RUN_POOLS.clear()
    for pool in pools:
        pool.close()


@contextmanager
def admission_session(postgres_url: str) -> Generator[psycopg.Connection, None, None]:
    """Lend one admission connection and return it idle.

    The caller commits or rolls back before leaving the block. A successful
    exit rolls back a leftover transaction and reuses the connection. Any
    exception rolls back best-effort and closes the connection.

    Args:
        postgres_url: Transaction-pooler URL. Never logged.

    Yields:
        Open connection. Autocommit stays off. No role is selected yet.

    Raises:
        psycopg.Error: Connect failure.
        OSError: Network failure before the driver wraps it.
    """
    connection = _checkout(postgres_url, kind="admission")
    reusable = False
    try:
        yield connection
        reusable = True
    except BaseException:
        _rollback_quietly(connection)
        raise
    finally:
        if reusable:
            reusable = _reuse_after_rollback(connection)
        _release(connection, reusable=reusable)


def checkout_run_connection(postgres_url: str) -> psycopg.Connection:
    """Lend one graph connection. The caller selects ``app_api`` and releases it.

    Args:
        postgres_url: Transaction-pooler URL. Never logged.

    Returns:
        Open connection with no role selected yet.

    Raises:
        psycopg.Error: Connect failure.
        OSError: Network failure before the driver wraps it.
    """
    return _checkout(postgres_url, kind="run")


def release_run_connection(connection: object, *, reusable: bool | None = None) -> None:
    """Return a graph connection to its pool, or close a direct connect.

    Connections this module did not lend are closed. That keeps tests and
    Studio stand-ins that only implement ``close()`` working.

    Args:
        connection: Object returned by :func:`checkout_run_connection`, or
            any object with ``close``.
        reusable: When omitted, roll back an open transaction and reuse only
            if the connection is idle. ``False`` always closes it.

    Side Effects:
        May close ``connection`` or leave it idle in the run pool.
    """
    if _checkout_for(connection) is None:
        _close_quietly(connection)
        return
    if reusable is None:
        reusable = _reuse_after_rollback(connection)
    _release(connection, reusable=reusable)


def _checkout(postgres_url: str, *, kind: str) -> psycopg.Connection:
    """Lend a pooled connection, or open one when every slot is lent.

    Args:
        postgres_url: Transaction-pooler URL.
        kind: ``admission`` or ``run``.

    Returns:
        Open connection registered for :func:`_release`.

    Raises:
        psycopg.Error: Connect failure. A pooled slot is freed first.
        OSError: Network failure before the driver wraps it.
    """
    pool = _pool(postgres_url, kind)
    try:
        connection = pool.acquire()
        pooled = True
    except PoolBusyError:
        connection = connect_postgres(postgres_url)
        pooled = False
    with _LOCK:
        _CHECKOUTS[id(connection)] = _Checkout(pool=pool, pooled=pooled)
    return connection


def _release(connection: object, *, reusable: bool) -> None:
    """Pop the checkout record and return or close ``connection``.

    Args:
        connection: Lent connection.
        reusable: True only when the session is idle and safe to lend again.
    """
    with _LOCK:
        checkout = _CHECKOUTS.pop(id(connection), None)
    if checkout is None:
        _close_quietly(connection)
        return
    if checkout.pooled:
        checkout.pool.release(cast(psycopg.Connection, connection), reusable=reusable)
        return
    _close_quietly(connection)


def _checkout_for(connection: object) -> _Checkout | None:
    """Return the checkout record for ``connection`` without removing it.

    Args:
        connection: Candidate connection.

    Returns:
        The record, or None when this module did not lend it.
    """
    with _LOCK:
        return _CHECKOUTS.get(id(connection))


def _pool(postgres_url: str, kind: str) -> BoundedConnectionPool:
    """Return the process pool for ``kind``, creating it on first use.

    Args:
        postgres_url: Transaction-pooler URL stored as the pool key.
        kind: ``admission`` or ``run``.

    Returns:
        Pool that has not connected yet when it was just created.
    """
    with _LOCK:
        pools = _ADMISSION_POOLS if kind == "admission" else _RUN_POOLS
        max_size = (
            ADMISSION_POOL_MAX_SIZE if kind == "admission" else RUN_POOL_MAX_SIZE
        )
        pool = pools.get(postgres_url)
        if pool is None:
            pool = BoundedConnectionPool(
                postgres_url,
                max_size=max_size,
                wait_seconds=API_POOL_WAIT_SECONDS,
                idle_seconds=API_POOL_IDLE_SECONDS,
                name=f"api-{kind}",
                connect=connect_postgres,
            )
            pools[postgres_url] = pool
        return pool


def _ready_to_reuse(connection: object) -> bool:
    """Return whether ``connection`` is open and has no transaction.

    Stand-ins without ``info`` count as idle so unit fakes can be reused.

    Args:
        connection: Pooled connection or test stand-in.

    Returns:
        True when the next borrower can start a transaction.
    """
    if bool(getattr(connection, "closed", False)):
        return False
    info = getattr(connection, "info", None)
    status = getattr(info, "transaction_status", None)
    if status is None:
        return True
    return status == TransactionStatus.IDLE


def _reuse_after_rollback(connection: object) -> bool:
    """Roll back an open transaction, then report whether reuse is safe.

    Args:
        connection: Connection about to return to a pool.

    Returns:
        True when the connection is open and idle after the attempt.
    """
    if _ready_to_reuse(connection):
        return True
    rollback = getattr(connection, "rollback", None)
    if not callable(rollback):
        return False
    try:
        rollback()
    except Exception:
        return False
    return _ready_to_reuse(connection)


def _rollback_quietly(connection: object) -> None:
    """Roll back ``connection`` and ignore rollback errors.

    Args:
        connection: Connection whose transaction may be aborted.
    """
    rollback = getattr(connection, "rollback", None)
    if not callable(rollback):
        return
    try:
        rollback()
    except Exception:
        LOGGER.info(
            "api postgres pool rollback failed",
            extra={
                "operation": "api_postgres_pool_rollback",
                "attempt": 1,
                "reason": "rollback_failed",
            },
        )


def _close_quietly(connection: object) -> None:
    """Close ``connection`` and ignore close errors.

    Args:
        connection: Connection or stand-in with ``close``.
    """
    closer = getattr(connection, "close", None)
    if not callable(closer):
        return
    try:
        closer()
    except Exception:
        return
