"""Contract tests for local-stack reachability isolation."""

from __future__ import annotations

import psycopg

from tests.contract.integration_support import (
    _local_supabase_runtime_ready,
    resolve_supabase_db_url,
    try_connect,
)


def test_try_connect_treats_incomplete_postgres_as_unreachable() -> None:
    """Vanilla local Postgres without ``app_worker`` is not a live stack.

    CPU/local contract runs must skip instead of erroring on ``SET ROLE``.
    """

    url = resolve_supabase_db_url()
    try:
        raw = psycopg.connect(url, connect_timeout=3)
    except psycopg.Error:
        assert try_connect(url) is None
        return
    try:
        ready = _local_supabase_runtime_ready(raw)
    finally:
        raw.close()
    wrapped = try_connect(url)
    if ready:
        assert wrapped is not None
        wrapped.close()
        return
    assert wrapped is None
