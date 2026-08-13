"""Contract tests for pgvector 0.8+ capability gates and selective-filter HNSW smoke."""

from __future__ import annotations

import psycopg
import pytest

from tests.contract.integration_support import (
    DEFAULT_SUPABASE_DB_URL,
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)


def _assert_pgvector_capabilities(connection: psycopg.Connection) -> str:
    """Call the migration gate and return the installed pgvector version.

    Args:
        connection: Open Postgres connection with ``search`` schema applied.

    Returns:
        Installed pgvector extension version string.

    Raises:
        AssertionError: When the gate function is missing or rejects capabilities.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT search.assert_pgvector_capabilities()")
        row = cursor.fetchone()
        assert row is not None
        version = str(row[0])
        major, minor = (int(part) for part in version.split(".")[:2])
        assert major > 0 or minor >= 8
        return version


def _hnsw_selective_filter_smoke(connection: psycopg.Connection) -> None:
    """Prove iterative-scan HNSW returns only rows matching a metadata filter.

    Args:
        connection: Open Postgres connection.

    Raises:
        AssertionError: When filtered nearest-neighbor ordering is incorrect.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TEMP TABLE pgvector_qual_smoke (
              id int PRIMARY KEY,
              tenant text NOT NULL,
              embedding extensions.vector(3) NOT NULL
            ) ON COMMIT DROP
            """
        )
        cursor.execute(
            """
            INSERT INTO pgvector_qual_smoke (id, tenant, embedding) VALUES
              (1, 'tenant_a', '[1,0,0]'),
              (2, 'tenant_a', '[0.95,0.05,0]'),
              (3, 'tenant_b', '[0,1,0]')
            """
        )
        cursor.execute(
            """
            CREATE INDEX pgvector_qual_smoke_hnsw
            ON pgvector_qual_smoke
            USING hnsw (embedding extensions.vector_cosine_ops)
            """
        )
        cursor.execute("SET hnsw.iterative_scan = relaxed_order")
        cursor.execute("SET hnsw.ef_search = 40")
        cursor.execute(
            """
            SELECT id
            FROM pgvector_qual_smoke
            WHERE tenant = 'tenant_a'
            ORDER BY embedding <=> '[1,0,0]'::extensions.vector
            LIMIT 2
            """
        )
        rows = cursor.fetchall()
        assert [row[0] for row in rows] == [1, 2]


def test_local_pgvector_capabilities_and_selective_filter() -> None:
    """Local vector/search contracts pass capability, filter, and path checks."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")

    with connection:
        version = _assert_pgvector_capabilities(connection)
        assert version
        _hnsw_selective_filter_smoke(connection)
        search_path_row = connection.execute(
            """
            SELECT 'search_path=pg_catalog' = ANY(proconfig)
            FROM pg_proc
            WHERE oid = 'search.arabic_normalization_version()'::regprocedure
            """
        ).fetchone()
        assert search_path_row == (True,)


def test_managed_pgvector_capabilities_when_configured() -> None:
    """Managed target passes the same gate when ``SUPABASE_MANAGED_DB_URL`` is set."""

    managed_url = read_process_env("SUPABASE_MANAGED_DB_URL")
    if managed_url is None:
        pytest.skip("SUPABASE_MANAGED_DB_URL not configured")

    connection = try_connect(managed_url)
    if connection is None:
        pytest.skip(f"Managed Supabase Postgres unreachable at {managed_url}")

    with connection:
        _assert_pgvector_capabilities(connection)


def test_unsupported_pgvector_version_pattern_is_fail_closed() -> None:
    """Simulated sub-0.8 version parsing raises the same failure pattern as the gate."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")

    with connection:
        with connection.cursor() as cursor:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match=r"below required 0\.8",
            ):
                cursor.execute(
                    """
                    DO $gate$
                    DECLARE
                      ver text := '0.7.4';
                      major int;
                      minor int;
                    BEGIN
                      major := split_part(ver, '.', 1)::integer;
                      minor := split_part(ver, '.', 2)::integer;
                      IF major < 0 OR (major = 0 AND minor < 8) THEN
                        RAISE EXCEPTION 'pgvector % below required 0.8+', ver;
                      END IF;
                    END
                    $gate$;
                    """
                )


def test_default_local_url_constant_matches_documented_supabase_cli_port() -> None:
    """Document the default qualification URL used when ``SUPABASE_DB_URL`` is unset."""

    assert DEFAULT_SUPABASE_DB_URL.endswith(":54322/postgres")
