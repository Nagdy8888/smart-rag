"""Create or rotate the LOGIN wrapper ``app_runtime``.

``app_api`` / ``app_worker`` stay NOLOGIN. Compose connects as this wrapper
then ``SET ROLE``. This is operator SQL against the cloud project, not a
migration. Re-run after rotating the wrapper password.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import psycopg
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_WRAPPER_ENV = "APP_RUNTIME_DB_PASSWORD"
GRANTED_ROLES = ("app_api", "app_worker", "app_checkpointer", "app_lightrag")
OPERATOR_DSN_ENV = "OPERATOR_SUPABASE_DB_URL"


def parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one gitignored env file.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to raw values.
    """

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value
    return values


def upsert_env(path: Path, key: str, value: str) -> None:
    """Insert or replace one key without rewriting unrelated lines.

    Args:
        path: Env file to update. Created when missing.
        key: Environment variable name.
        value: Value to store. Never logged.
    """

    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    found = False
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing = stripped.split("=", 1)[0].strip()
            if existing == key:
                out.append(f"{key}={value}")
                found = True
                continue
        out.append(raw)
    if not found:
        if out and out[-1] != "":
            out.append("")
        out.append("# LOGIN wrapper for Compose API/worker (app_api is NOLOGIN)")
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def resolve_admin_dsn() -> str:
    """Return the operator DSN for creating or rotating ``app_runtime``.

    Reads ``OPERATOR_SUPABASE_DB_URL`` from the process environment first,
    then from gitignored ``.env.compose``. There is no local fixture default.

    Returns:
        Non-empty operator Postgres DSN. Never logged.

    Raises:
        RuntimeError: When the variable is unset in both sources.
    """

    process_value = os.environ.get(OPERATOR_DSN_ENV, "").strip()
    if process_value:
        return process_value
    compose_value = (
        parse_env(REPO_ROOT / ".env.compose").get(OPERATOR_DSN_ENV, "").strip()
    )
    if compose_value:
        return compose_value
    raise RuntimeError(
        "OPERATOR_SUPABASE_DB_URL is required; the local fixture default was removed"
    )


def resolve_runtime_password() -> str:
    """Return ``APP_RUNTIME_DB_PASSWORD`` from env files, generating if needed.

    Returns:
        Password string. Printed only as a length, never in plaintext.

    Side Effects:
        Writes the password into gitignored ``.env`` and ``.env.compose`` when
        missing so Compose interpolation can succeed.
    """

    process_value = os.environ.get(RUNTIME_WRAPPER_ENV, "").strip()
    compose_values = parse_env(REPO_ROOT / ".env.compose")
    local_values = parse_env(REPO_ROOT / ".env")
    password = (
        process_value
        or compose_values.get(RUNTIME_WRAPPER_ENV, "").strip()
        or local_values.get(RUNTIME_WRAPPER_ENV, "").strip()
    )
    if not password:
        password = secrets.token_urlsafe(24)
    for name in (".env", ".env.compose"):
        upsert_env(REPO_ROOT / name, RUNTIME_WRAPPER_ENV, password)
    return password


def ensure_role(*, admin_dsn: str, password: str) -> None:
    """Create ``app_runtime`` and grant NOLOGIN application roles.

    Args:
        admin_dsn: Operator Postgres DSN used only for this script.
        password: LOGIN password for ``app_runtime``.

    Raises:
        psycopg.Error: When Postgres is unreachable or GRANT fails.
    """

    with psycopg.connect(admin_dsn, connect_timeout=10) as connection:
        connection.execute("SELECT 1")
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime'"
        ).fetchone()
        if exists is None:
            connection.execute(
                sql.SQL(
                    "CREATE ROLE app_runtime LOGIN PASSWORD {} "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT"
                ).format(sql.Literal(password))
            )
        else:
            connection.execute(
                sql.SQL("ALTER ROLE app_runtime LOGIN PASSWORD {}").format(
                    sql.Literal(password)
                )
            )
        for role in GRANTED_ROLES:
            role_exists = connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s",
                (role,),
            ).fetchone()
            if role_exists is None:
                raise RuntimeError(f"required role {role} is missing")
            connection.execute(
                sql.SQL("GRANT {} TO app_runtime").format(sql.Identifier(role))
            )
        connection.commit()


def main() -> int:
    """Ensure the Compose LOGIN wrapper exists and env files carry its password.

    Returns:
        ``0`` on success, ``1`` when the operator DSN is missing, Postgres
        is unreachable, or required roles are missing.

    Side Effects:
        Connects as the operator role. Writes gitignored env files. Prints
        role name and password length only.
    """

    password = resolve_runtime_password()
    print(f"{RUNTIME_WRAPPER_ENV}_len={len(password)}")
    try:
        ensure_role(admin_dsn=resolve_admin_dsn(), password=password)
    except psycopg.Error as exc:
        print(f"Postgres unavailable: {type(exc).__name__}")
        print("Check OPERATOR_SUPABASE_DB_URL and network access to the cloud pooler")
        return 1
    except RuntimeError as exc:
        print(str(exc))
        return 1
    print("app_runtime LOGIN wrapper ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
