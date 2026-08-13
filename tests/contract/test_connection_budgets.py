"""Connection budget and role-setting contract tests (Phase 2 Packet 6)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import yaml

from tests.contract.integration_support import resolve_supabase_db_url, try_connect

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"

# Proven inventory: single api + single worker (no replicas) + reserved ops.
WORST_CASE_CAPS = {
    "api_txn": 10,
    "api_checkpointer_session": 4,
    "api_lightrag_session": 4,
    "worker_txn": 6,
    "worker_lightrag_session": 4,
    "operations": 2,
}
SELECTED_TIER_HARD_LIMIT = 60  # Free/Nano-class managed smart-rag
BUDGET_CEILING = int(SELECTED_TIER_HARD_LIMIT * 0.7)  # 42

EXPECTED_ROLE_SETTINGS: dict[str, dict[str, str]] = {
    "app_api": {
        "statement_timeout": "15s",
        "lock_timeout": "2s",
        "idle_in_transaction_session_timeout": "5s",
        "work_mem": "8MB",
        "application_name": "smart-rag-api",
    },
    "app_worker": {
        "statement_timeout": "60s",
        "lock_timeout": "5s",
        "idle_in_transaction_session_timeout": "15s",
        "work_mem": "16MB",
        "application_name": "smart-rag-worker",
    },
    "app_checkpointer": {
        "statement_timeout": "30s",
        "lock_timeout": "3s",
        "idle_in_transaction_session_timeout": "10s",
        "work_mem": "16MB",
        "application_name": "smart-rag-checkpointer",
    },
    "app_lightrag": {
        "statement_timeout": "120s",
        "lock_timeout": "5s",
        "idle_in_transaction_session_timeout": "30s",
        "work_mem": "16MB",
        "application_name": "smart-rag-lightrag",
    },
    "app_audit_writer": {
        "statement_timeout": "15s",
        "lock_timeout": "2s",
        "idle_in_transaction_session_timeout": "5s",
        "work_mem": "8MB",
        "application_name": "smart-rag-audit",
    },
}


def _parse_rolconfig(raw: list[str] | None) -> dict[str, str]:
    """Parse ``pg_roles.rolconfig`` entries into a setting map."""

    parsed: dict[str, str] = {}
    if not raw:
        return parsed
    for item in raw:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parsed[key] = value
    return parsed


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_worst_case_connection_budget_under_seventy_percent() -> None:
    """Document compose process inventory and prove 30 < 42 at Nano 60 hard limit."""

    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = compose["services"]
    assert "api" in services
    assert "worker" in services
    assert "deploy" not in services["api"] or "replicas" not in services["api"].get(
        "deploy", {}
    )
    assert "deploy" not in services["worker"] or "replicas" not in services[
        "worker"
    ].get("deploy", {})

    worst_case = sum(WORST_CASE_CAPS.values())
    assert worst_case == 30
    assert BUDGET_CEILING == 42
    assert worst_case < BUDGET_CEILING
    assert worst_case < SELECTED_TIER_HARD_LIMIT * 0.7


def test_role_timeouts_and_application_name_introspected(
    db_connection: psycopg.Connection,
) -> None:
    """Prove ALTER ROLE timeout/work_mem/application_name settings via pg_roles."""

    with db_connection.cursor() as cursor:
        for role_name, expected in EXPECTED_ROLE_SETTINGS.items():
            cursor.execute(
                "SELECT rolconfig FROM pg_roles WHERE rolname = %s",
                (role_name,),
            )
            row = cursor.fetchone()
            assert row is not None, f"missing role {role_name}"
            settings = _parse_rolconfig(row[0])
            for key, value in expected.items():
                assert settings.get(key) == value, (
                    f"{role_name}.{key}: expected {value!r}, got {settings.get(key)!r}"
                )


def test_app_api_can_connect_and_validate_without_session_gucs(
    db_connection: psycopg.Connection,
) -> None:
    """Prove app_api SET ROLE works and validate_caller_context uses typed args only.

    Transaction-pool safety: identity is passed as RPC arguments, never session
    GUCs such as ``request.jwt.claims``.
    """

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_get_functiondef(p.oid)
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app' AND p.proname = 'validate_caller_context'
            """
        )
        row = cursor.fetchone()
        assert row is not None
        function_def = row[0]
        assert "set_config" not in function_def.lower()
        assert "request.jwt" not in function_def.lower()
        assert "current_setting" not in function_def.lower()

        cursor.execute("SET ROLE app_api")
        cursor.execute("SELECT app.validate_caller_context(NULL, NULL, NULL)")
        validation = cursor.fetchone()
        assert validation is not None
        assert validation[0] is False

        cursor.execute("RESET ROLE")
        cursor.execute("SELECT current_setting('role', true)")
        # After RESET ROLE the session user is restored; no leaked caller GUC.
        cursor.execute(
            """
            SELECT name
            FROM pg_settings
            WHERE name LIKE 'app.%' OR name LIKE 'request.%'
            """
        )
        leaked = cursor.fetchall()
        assert leaked == []
