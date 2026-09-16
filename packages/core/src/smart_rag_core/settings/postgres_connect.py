"""Psycopg connections that stay safe on hosted transaction poolers."""

from __future__ import annotations

from typing import Any

import psycopg


def connect_postgres(conninfo: str, **kwargs: Any) -> psycopg.Connection:
    """Open Postgres with automatic prepared statements disabled.

    Hosted Supabase transaction poolers (port 6543 / Supavisor) reuse backend
    sessions across clients. Psycopg 3's default named prepares then raise
    ``DuplicatePreparedStatement`` on the next checkout. SSE event-store and
    LangGraph checkpointer already disable prepares; query retrieve and persist
    must do the same.

    Args:
        conninfo: Postgres DSN. Callers must not log this value.
        **kwargs: Extra ``psycopg.connect`` keyword arguments. Callers may
            override ``prepare_threshold`` only in tests that need it.

    Returns:
        An open connection.

    Raises:
        psycopg.Error: Connection or authentication failure.
        OSError: Network failure before the driver wraps it.
    """

    kwargs.setdefault("prepare_threshold", None)
    return psycopg.connect(conninfo, **kwargs)
