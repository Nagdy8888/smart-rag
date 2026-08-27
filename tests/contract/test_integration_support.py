"""Contract tests for local-stack reachability isolation."""

from __future__ import annotations

import psycopg
import pytest

from tests.contract.integration_support import (
    local_supabase_runtime_ready,
    refuse_hosted_destructive_dsn,
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
        ready = local_supabase_runtime_ready(raw)
    finally:
        raw.close()
    wrapped = try_connect(url)
    if ready:
        assert wrapped is not None
        wrapped.close()
        return
    assert wrapped is None


def test_refuse_hosted_destructive_dsn_rejects_supabase_hosts() -> None:
    """Destructive suites cannot target hosted or pooler hostnames."""

    with pytest.raises(RuntimeError, match="destructive_tests_refuse_hosted_supabase"):
        refuse_hosted_destructive_dsn(
            "postgresql://app_runtime:secret@db.example.supabase.co:5432/postgres"
        )
    with pytest.raises(RuntimeError, match="destructive_tests_refuse_hosted_supabase"):
        refuse_hosted_destructive_dsn(
            "postgresql://app_runtime:secret@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
        )
    refuse_hosted_destructive_dsn(
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )
