"""Contract tests for LightRAG private-schema bootstrap and runtime attach.

Live tests skip when local Supabase Postgres is unreachable unless
``SMART_RAG_REQUIRE_JOB_INTEGRATION=1``, in which case they fail closed.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.gateways.model import create_model_gateway
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    LIGHTRAG_RUNTIME_ROLE,
    RUNTIME_POSTGRES_MAX_CONNECTIONS,
)
from smart_rag_core.retrieval.lightrag_adapter import (
    LightRagAdapterError,
    LightRagRuntimeAdapterContext,
    apply_lightrag_postgres_env,
    load_reviewed_fingerprint_fixture,
    open_runtime_lightrag_adapter,
    public_vendor_tables,
    reviewed_schema_manifest,
)
from smart_rag_core.retrieval.lightrag_bootstrap import (
    bootstrap_lightrag_schema,
    persist_capture_status,
    repeat_bootstrap_lightrag_schema,
)
from smart_rag_core.retrieval.lightrag_qualification import (
    LightRagPostgresParams,
    is_fatal_initialize_warning,
    parse_postgres_url,
    reset_process_client_manager,
)
from smart_rag_core.settings import SharedSettings

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "lightrag" / "schema_fingerprint_v1.json"
_POSTGRES_ENV_KEYS = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DATABASE",
    "POSTGRES_MAX_CONNECTIONS",
    "POSTGRES_CONNECTION_RETRIES",
    "POSTGRES_SERVER_SETTINGS",
    "POSTGRES_WORKSPACE",
    "WORKSPACE",
)


def _require_postgres() -> tuple[str, LightRagPostgresParams]:
    """Open Postgres or skip unless the job integration gate is required.

    Returns:
        URL and parsed connection fields. The URL is never logged.

    Raises:
        pytest.fail: When the integration gate is required and Postgres is down.
    """

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("LightRAG bootstrap requires reachable Supabase Postgres")
        pytest.skip("Local Supabase Postgres unreachable")
    connection.close()
    return url, parse_postgres_url(url)


@pytest.fixture
def postgres_url() -> Iterator[str]:
    """Yield the local Postgres URL or skip when unreachable."""

    url, _params = _require_postgres()
    del _params
    yield url


@pytest.fixture(autouse=True)
def restore_postgres_env() -> Iterator[None]:
    """Restore ``POSTGRES_*`` keys after each test. Values are not logged."""

    snapshot = {key: os.environ.get(key) for key in _POSTGRES_ENV_KEYS}
    try:
        yield
    finally:
        for key, value in snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True)
def forbid_runtime_pipmaster_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed if LightRAG attempts a runtime ``pipmaster.install``."""

    def _blocked(*_args: object, **_kwargs: object) -> None:
        """Reject unexpected runtime package installation."""

        raise AssertionError("pipmaster.install must not run during bootstrap")

    monkeypatch.setattr("pipmaster.install", _blocked)
    try:
        import lightrag.kg.postgres_impl as postgres_impl

        monkeypatch.setattr(postgres_impl.pm, "install", _blocked)
    except ImportError:
        return


def _gateways() -> tuple[object, object]:
    """Return mock embedding and model gateways."""

    settings = SharedSettings(mock_model_mode=True)
    return create_embedding_gateway(settings), create_model_gateway(settings)


def _secret(url: str) -> SecretStr:
    """Wrap a URL as a secret without logging it.

    Args:
        url: Postgres URL.

    Returns:
        Secret wrapper.
    """

    return SecretStr(url)


def test_fresh_and_repeat_bootstrap_match_reviewed_fingerprint(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Fresh and repeat bootstrap must match the reviewed table list."""

    asyncio.run(_fresh_and_repeat_bootstrap(postgres_url, monkeypatch, tmp_path))


async def _fresh_and_repeat_bootstrap(
    url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for bootstrap fingerprint stability.

    Args:
        url: Postgres URL.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    embedding_gateway, model_gateway = _gateways()
    dsn = _secret(url)
    connection = psycopg.connect(url)
    try:
        first = await bootstrap_lightrag_schema(
            schema_admin_dsn=dsn,
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "boot1",
            connection=connection,
        )
        persist_capture_status(connection, first)
        assert first.fingerprint.tables == reviewed_schema_manifest().tables
        assert (
            first.fingerprint.tables
            == load_reviewed_fingerprint_fixture(FIXTURE).tables
        )
        for message in (
            *first.warnings.python_warnings,
            *first.warnings.log_warnings,
        ):
            assert is_fatal_initialize_warning(message) is False
        second = await repeat_bootstrap_lightrag_schema(
            schema_admin_dsn=dsn,
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "boot2",
            connection=connection,
            first=first,
        )
        assert second.fingerprint_sha256 == first.fingerprint_sha256
    finally:
        connection.close()
        await reset_process_client_manager()


def test_runtime_role_dml_without_ddl(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Runtime attach uses DML only; CREATE as app_lightrag is denied."""

    asyncio.run(_runtime_role_dml_without_ddl(postgres_url, monkeypatch, tmp_path))


async def _runtime_role_dml_without_ddl(
    url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for runtime attach and DDL denial.

    Args:
        url: Postgres URL.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    embedding_gateway, model_gateway = _gateways()
    connection = psycopg.connect(url)
    adapter = None
    try:
        adapter = await open_runtime_lightrag_adapter(
            dsn=_secret(url),
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "runtime",
            workspace=DEFAULT_GRAPH_WORKSPACE,
            connection=connection,
            max_connections=RUNTIME_POSTGRES_MAX_CONNECTIONS,
        )
        assert adapter.fingerprint.tables == reviewed_schema_manifest().tables
        assert await adapter.current_database_user() == LIGHTRAG_RUNTIME_ROLE
        pool_max = adapter.client_pool_max_size()
        assert pool_max is not None
        assert pool_max <= RUNTIME_POSTGRES_MAX_CONNECTIONS
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE app_lightrag")
            cursor.execute("SELECT count(*) FROM lightrag.lightrag_graph_nodes")
            assert cursor.fetchone() is not None
            cursor.execute("SAVEPOINT denied_ddl")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    "CREATE TABLE lightrag.runtime_forbidden_ddl (id integer PRIMARY KEY)"
                )
            cursor.execute("ROLLBACK TO SAVEPOINT denied_ddl")
            cursor.execute("RELEASE SAVEPOINT denied_ddl")
            cursor.execute("RESET ROLE")
    finally:
        if adapter is not None:
            await adapter.finalize()
        connection.close()
        await reset_process_client_manager()


def test_anon_authenticated_cannot_read_vendor_tables(
    postgres_url: str,
) -> None:
    """Browser-facing roles must not SELECT private vendor tables."""

    connection = psycopg.connect(postgres_url)
    try:
        with connection.cursor() as cursor:
            for role_name in ("anon", "authenticated"):
                cursor.execute(f"SET ROLE {role_name}")
                cursor.execute("SAVEPOINT denied_vendor_read")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute("SELECT count(*) FROM lightrag.lightrag_graph_nodes")
                cursor.execute("ROLLBACK TO SAVEPOINT denied_vendor_read")
                cursor.execute("RELEASE SAVEPOINT denied_vendor_read")
                cursor.execute("RESET ROLE")
            cursor.execute(
                """
                SELECT 1
                FROM pg_roles
                WHERE rolname = 'service_role'
                """
            )
            if cursor.fetchone() is not None:
                cursor.execute("SET ROLE service_role")
                cursor.execute("SAVEPOINT denied_service_role")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute("SELECT count(*) FROM lightrag.lightrag_graph_nodes")
                cursor.execute("ROLLBACK TO SAVEPOINT denied_service_role")
                cursor.execute("RELEASE SAVEPOINT denied_service_role")
                cursor.execute("RESET ROLE")
    finally:
        connection.close()


def test_vendor_tables_absent_from_public(postgres_url: str) -> None:
    """Vendor-named tables must not leak into schema ``public``."""

    connection = psycopg.connect(postgres_url)
    try:
        assert public_vendor_tables(connection) == ()
    finally:
        connection.close()


def test_postgres_workspace_override_fails_before_attach(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``POSTGRES_WORKSPACE`` must fail closed before runtime attach."""

    monkeypatch.setenv("POSTGRES_WORKSPACE", "collapse")
    embedding_gateway, model_gateway = _gateways()
    connection = psycopg.connect(postgres_url)
    try:
        with pytest.raises(
            LightRagAdapterError, match="postgres_workspace_env_override"
        ):
            asyncio.run(
                open_runtime_lightrag_adapter(
                    dsn=_secret(postgres_url),
                    embedding_gateway=embedding_gateway,
                    model_gateway=model_gateway,
                    working_dir=tmp_path / "override",
                    connection=connection,
                )
            )
    finally:
        connection.close()


def test_wrong_search_path_env_fails_closed(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Applying a public search_path must fail closed."""

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    params = parse_postgres_url(postgres_url)
    with pytest.raises(LightRagAdapterError, match="wrong_search_path"):
        apply_lightrag_postgres_env(
            params,
            max_connections=2,
            server_settings="search_path=public",
        )


def test_unfinalized_shutdown_context_manager(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Adapter context manager finalizes even when the body raises."""

    asyncio.run(_unfinalized_shutdown(postgres_url, monkeypatch, tmp_path))


async def _unfinalized_shutdown(
    url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for unfinalized shutdown coverage.

    Args:
        url: Postgres URL.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    embedding_gateway, model_gateway = _gateways()
    connection = psycopg.connect(url)
    try:
        adapter = await open_runtime_lightrag_adapter(
            dsn=_secret(url),
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "ctx",
            connection=connection,
        )
        with pytest.raises(RuntimeError, match="forced_unfinalized"):
            async with LightRagRuntimeAdapterContext(adapter):
                raise RuntimeError("forced_unfinalized")
        assert adapter.client_pool_max_size() is None
    finally:
        connection.close()
        await reset_process_client_manager()


def test_second_factory_does_not_exceed_pool_cap(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A second factory after finalize must not leak past cap 4."""

    asyncio.run(_second_factory_pool_cap(postgres_url, monkeypatch, tmp_path))


async def _second_factory_pool_cap(
    url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for pool-cap reuse after finalize.

    Args:
        url: Postgres URL.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    embedding_gateway, model_gateway = _gateways()
    connection = psycopg.connect(url)
    first = None
    second = None
    try:
        first = await open_runtime_lightrag_adapter(
            dsn=_secret(url),
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "pool1",
            connection=connection,
        )
        first_max = first.client_pool_max_size()
        assert first_max is not None
        assert first_max <= RUNTIME_POSTGRES_MAX_CONNECTIONS
        await first.finalize()
        first = None
        second = await open_runtime_lightrag_adapter(
            dsn=_secret(url),
            embedding_gateway=embedding_gateway,
            model_gateway=model_gateway,
            working_dir=tmp_path / "pool2",
            connection=connection,
        )
        second_max = second.client_pool_max_size()
        assert second_max is not None
        assert second_max <= RUNTIME_POSTGRES_MAX_CONNECTIONS
    finally:
        if first is not None:
            await first.finalize()
        if second is not None:
            await second.finalize()
        connection.close()
        await reset_process_client_manager()


def test_incompatible_dimension_fails_closed(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Attaching with a non-1024 embedding dimension fails closed."""

    asyncio.run(_incompatible_dimension(postgres_url, monkeypatch, tmp_path))


async def _incompatible_dimension(
    url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Async body for incompatible embedding dimension.

    Args:
        url: Postgres URL.
        monkeypatch: Environment helper.
        tmp_path: Per-test working directory.
    """

    from smart_rag_core.retrieval import lightrag_adapter as adapter_mod

    monkeypatch.delenv("POSTGRES_WORKSPACE", raising=False)
    monkeypatch.setattr(adapter_mod, "EMBEDDING_DIMENSIONS", 1536)
    embedding_gateway, model_gateway = _gateways()
    connection = psycopg.connect(url)
    try:
        with pytest.raises(
            LightRagAdapterError,
            match=r"incompatible_vector_config|schema_drift_missing_vector_table",
        ):
            await open_runtime_lightrag_adapter(
                dsn=_secret(url),
                embedding_gateway=embedding_gateway,
                model_gateway=model_gateway,
                working_dir=tmp_path / "dim",
                connection=connection,
            )
    finally:
        connection.close()
        await reset_process_client_manager()
