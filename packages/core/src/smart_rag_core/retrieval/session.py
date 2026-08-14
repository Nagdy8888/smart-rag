"""Transaction-local retrieval session: role, timeout, and HNSW GUCs.

Direct/pooled SQL does not inherit Supabase JWT identity. FastAPI must verify
the token, resolve ``CallerContext``, then run RPCs inside this transaction.
``SET LOCAL`` values do not survive commit, rollback, or pooled reuse.
Passing caller IDs as client authority is forbidden; the RPC rechecks live
profile and authorization version.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Literal

import psycopg
from psycopg.pq import TransactionStatus

from smart_rag_core.retrieval.profiles import (
    HnswProfileId,
    HnswProfileSettings,
    resolve_hnsw_profile,
)
from smart_rag_core.security.identity import CallerContext

RetrievalLanguage = Literal["en", "ar", "mixed"]


class RetrievalSessionError(RuntimeError):
    """Raised when the retrieval transaction cannot start safely."""


def _require_idle(connection: psycopg.Connection) -> None:
    """Fail closed when the connection already has an open transaction.

    Args:
        connection: psycopg connection that must be idle.

    Raises:
        RetrievalSessionError: If a transaction is already in progress.
    """

    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise RetrievalSessionError("retrieval_requires_idle_connection")


def apply_hnsw_settings(
    connection: psycopg.Connection,
    settings: HnswProfileSettings,
) -> None:
    """Apply transaction-local HNSW and statement bounds via ``set_config``.

    Args:
        connection: Open connection inside a transaction.
        settings: Allow-listed profile. ``strict_order`` does not make HNSW exact.

    Side Effects:
        Sets ``SET LOCAL`` GUCs for the current transaction only.
    """

    pairs = (
        ("hnsw.iterative_scan", settings.iterative_scan),
        ("hnsw.ef_search", str(settings.ef_search)),
        ("hnsw.max_scan_tuples", str(settings.max_scan_tuples)),
        ("hnsw.scan_mem_multiplier", str(settings.scan_mem_multiplier)),
        ("work_mem", settings.work_mem),
        ("statement_timeout", str(settings.statement_timeout_ms)),
    )
    with connection.cursor() as cursor:
        for name, value in pairs:
            cursor.execute(
                "SELECT set_config(%s, %s, true)",
                (name, value),
            )


@contextmanager
def retrieval_transaction(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    profile: HnswProfileId | str = HnswProfileId.LOW,
    apply_hnsw: bool = True,
) -> Generator[psycopg.Connection, None, None]:
    """Run one retrieval RPC batch as ``app_api`` with transaction-local GUCs.

    Args:
        connection: Privileged login connection that can ``SET ROLE app_api``.
        caller: Server-derived identity. Must not be disabled.
        profile: Allow-listed HNSW profile.
        apply_hnsw: When false, only role and statement timeout are set (term/recheck).

    Yields:
        The same connection, now inside an ``app_api`` transaction.

    Raises:
        RetrievalSessionError: If the caller is disabled or the connection is busy.
        ValueError: If the profile is not allow-listed.

    Side Effects:
        Begins a transaction, sets ``SET LOCAL ROLE app_api`` and GUCs, then
        commits on success or rolls back on error.
    """

    if caller.disabled:
        raise RetrievalSessionError("caller_disabled")
    settings = resolve_hnsw_profile(profile)
    _require_idle(connection)
    with connection.transaction():
        connection.execute("SET LOCAL ROLE app_api")
        if apply_hnsw:
            apply_hnsw_settings(connection, settings)
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config(%s, %s, true)",
                    ("statement_timeout", str(settings.statement_timeout_ms)),
                )
        yield connection
