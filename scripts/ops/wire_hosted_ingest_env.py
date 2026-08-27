"""Probe hosted roles and wire laptop Compose to hosted app_runtime DSNs.

Does not print secrets. Does not start EC2. Operator uses the existing
session pooler URL (postgres) only to CREATE/GRANT ``app_runtime``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ensure_app_runtime_role import (
    GRANTED_ROLES,
    ensure_role,
    parse_env,
    resolve_runtime_password,
    upsert_env,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _require(env: dict[str, str], key: str) -> str:
    """Return a required env value.

    Args:
        env: Parsed env mapping.
        key: Variable name.

    Returns:
        Non-empty value.

    Raises:
        RuntimeError: When the key is missing or empty.
    """

    value = env.get(key, "").strip().strip('"').strip("'")
    if not value:
        raise RuntimeError(f"missing_{key}")
    return value


def _rewrite_pooler_user(dsn: str, *, user: str, password: str) -> str:
    """Replace the pooler login with ``user.projectref`` and a new password.

    Args:
        dsn: Existing Supabase pooler URI (usually ``postgres.PROJECTREF``).
        user: LOGIN role such as ``app_runtime``.
        password: LOGIN password. Never logged.

    Returns:
        Rewritten URI.

    Raises:
        RuntimeError: If the source username has no project-ref suffix.
    """

    parsed = urlparse(dsn)
    current_user = parsed.username or ""
    if "." not in current_user:
        raise RuntimeError("pooler_username_missing_project_ref")
    _, project_ref = current_user.split(".", 1)
    new_user = f"{user}.{project_ref}"
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{quote(new_user, safe='.')}:{quote(password, safe='')}@{host}{port}"
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path or "/postgres",
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _classify(dsn: str) -> str:
    """Return host/user labels without secrets.

    Args:
        dsn: Postgres URI.

    Returns:
        Classification string.
    """

    parsed = urlparse(dsn)
    user = parsed.username or ""
    host = parsed.hostname or ""
    port = parsed.port or 0
    return f"user={user.split('.')[0]} host_suffix={host[-20:]} port={port}"


def _role_names(admin_dsn: str) -> tuple[str, ...]:
    """List application-related roles on the hosted database.

    Args:
        admin_dsn: Operator session URL.

    Returns:
        Role names that exist.
    """

    wanted = ("app_runtime", *GRANTED_ROLES)
    with psycopg.connect(admin_dsn, connect_timeout=15) as connection:
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
            (list(wanted),),
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


def main() -> int:
    """Ensure hosted ``app_runtime`` and write Compose DSN overrides.

    Returns:
        Process exit code.

    Side Effects:
        Creates/alters hosted ``app_runtime``. Writes gitignored
        ``.env.compose`` keys. Never prints passwords or full URIs.
    """

    local_env = parse_env(REPO_ROOT / ".env")
    compose_env = parse_env(REPO_ROOT / ".env.compose")
    admin_dsn = _require(local_env, "STAGING_SUPABASE_SESSION_URL")
    transaction_dsn = _require(local_env, "STAGING_SUPABASE_TRANSACTION_URL")
    supabase_url = (
        local_env.get("SUPABASE_MANAGED_URL")
        or local_env.get("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).strip()
    if "supabase.co" not in supabase_url:
        raise RuntimeError("hosted_supabase_url_missing")

    roles = _role_names(admin_dsn)
    print("hosted_roles=" + ",".join(roles) if roles else "hosted_roles=none")
    missing_grants = [role for role in GRANTED_ROLES if role not in roles]
    if missing_grants:
        print("blocked_missing_nologin_roles=" + ",".join(missing_grants))
        print("apply hosted migrations before Phase A ingest")
        return 1

    password = resolve_runtime_password()
    ensure_role(admin_dsn=admin_dsn, password=password)
    print("app_runtime_login=ready")

    api_dsn = _rewrite_pooler_user(
        transaction_dsn, user="app_runtime", password=password
    )
    worker_dsn = _rewrite_pooler_user(admin_dsn, user="app_runtime", password=password)
    parsed_api = urlparse(api_dsn)
    parsed_worker = urlparse(worker_dsn)
    if (parsed_api.username or "").startswith("postgres"):
        raise RuntimeError("api_dsn_still_postgres")
    if (parsed_worker.username or "").startswith("postgres"):
        raise RuntimeError("worker_dsn_still_postgres")

    compose_path = REPO_ROOT / ".env.compose"
    upsert_env(compose_path, "SUPABASE_URL", supabase_url)
    upsert_env(compose_path, "NEXT_PUBLIC_SUPABASE_URL", supabase_url)
    upsert_env(compose_path, "API_SUPABASE_DB_URL", api_dsn)
    upsert_env(compose_path, "WORKER_SUPABASE_DB_URL", worker_dsn)
    upsert_env(compose_path, "LANGGRAPH_CHECKPOINT_URL", worker_dsn)
    upsert_env(compose_path, "LIGHTRAG_DB_URL", worker_dsn)
    upsert_env(compose_path, "OPERATOR_SUPABASE_DB_URL", admin_dsn)
    anon_key = (
        local_env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or local_env.get("SUPABASE_ANON_KEY")
        or compose_env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if anon_key:
        upsert_env(compose_path, "NEXT_PUBLIC_SUPABASE_ANON_KEY", anon_key)
    upsert_env(compose_path, "APP_ENV", compose_env.get("APP_ENV", "local") or "local")
    upsert_env(compose_path, "MOCK_MODEL_MODE", "false")
    upsert_env(compose_path, "LANGSMITH_TRACING", "true")
    print("wrote=.env.compose")
    print("SUPABASE_URL=hosted")
    print("NEXT_PUBLIC_SUPABASE_URL=hosted")
    print("NEXT_PUBLIC_SUPABASE_ANON_KEY=" + ("present" if anon_key else "missing"))
    print("API_SUPABASE_DB_URL " + _classify(api_dsn))
    print("WORKER_SUPABASE_DB_URL " + _classify(worker_dsn))
    print("LANGGRAPH_CHECKPOINT_URL " + _classify(worker_dsn))
    print("LIGHTRAG_DB_URL " + _classify(worker_dsn))
    print("OPERATOR_SUPABASE_DB_URL user=postgres (operator only, not Compose)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
