"""Rebuild api/worker and pin them to local session DSNs. No secret prints."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one env file."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    """Build current images, then recreate api/worker on local 54321/54322."""

    merged: dict[str, str] = {}
    merged.update(_parse_env(ROOT / ".env"))
    merged.update(_parse_env(ROOT / ".env.compose"))
    password = merged.get("APP_RUNTIME_DB_PASSWORD", "")
    if not password:
        print("missing_APP_RUNTIME_DB_PASSWORD")
        return 1
    dsn = (
        "postgresql://app_runtime:"
        + quote(password, safe="")
        + "@host.docker.internal:54322/postgres"
    )
    compose = [
        "docker",
        "compose",
        "--env-file",
        ".env.compose",
        "-f",
        "docker-compose.yml",
    ]
    print("building_api_worker")
    built = subprocess.run(
        [*compose, "build", "api", "worker"],
        cwd=ROOT,
        check=False,
    )
    print(f"build_exit={built.returncode}")
    if built.returncode != 0:
        return built.returncode
    pin = [
        "-e",
        "SUPABASE_URL=http://host.docker.internal:54321",
        "-e",
        f"API_SUPABASE_DB_URL={dsn}",
        "-e",
        f"WORKER_SUPABASE_DB_URL={dsn}",
        "-e",
        f"LANGGRAPH_CHECKPOINT_URL={dsn}",
        "-e",
        f"LIGHTRAG_DB_URL={dsn}",
        "-e",
        "MOCK_MODEL_MODE=false",
        "-e",
        "NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321",
    ]
    os.environ["SUPABASE_URL"] = "http://host.docker.internal:54321"
    os.environ["API_SUPABASE_DB_URL"] = dsn
    os.environ["WORKER_SUPABASE_DB_URL"] = dsn
    os.environ["LANGGRAPH_CHECKPOINT_URL"] = dsn
    os.environ["LIGHTRAG_DB_URL"] = dsn
    os.environ["MOCK_MODEL_MODE"] = "false"
    os.environ["NEXT_PUBLIC_SUPABASE_URL"] = "http://127.0.0.1:54321"
    print("recreating_api_worker_local_session")
    up = subprocess.run(
        [
            *compose,
            "up",
            "-d",
            "--no-build",
            "--wait",
            "--wait-timeout",
            "300",
            "api",
            "worker",
        ],
        cwd=ROOT,
        check=False,
    )
    print(f"up_exit={up.returncode}")
    return up.returncode


if __name__ == "__main__":
    raise SystemExit(main())
