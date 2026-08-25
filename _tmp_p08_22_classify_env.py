"""Classify gitignored Compose DSNs without printing secrets."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "ops"))
from ensure_app_runtime_role import _parse_env, _upsert_env

REPO = Path(__file__).resolve().parent
REQUIRED = (
    "SUPABASE_URL",
    "API_SUPABASE_DB_URL",
    "WORKER_SUPABASE_DB_URL",
    "LANGGRAPH_CHECKPOINT_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
)


def _classify(name: str, value: str) -> str:
    """Return host/user labels without secrets.

    Args:
        name: Environment name.
        value: Raw value. Never printed.

    Returns:
        Classification string.
    """

    if not value:
        return f"{name} unset"
    parsed = urlparse(value)
    host = parsed.hostname or ""
    user = (parsed.username or "").split(".")[0]
    hosted = host.endswith(".supabase.co") or host.endswith("pooler.supabase.com")
    if parsed.scheme in {"http", "https"}:
        return (
            f"{name} scheme={parsed.scheme} host_suffix={host[-24:]} "
            f"port={parsed.port or 'default'} hosted={hosted}"
        )
    return (
        f"{name} user={user} host_suffix={host[-24:]} "
        f"port={parsed.port} hosted={hosted}"
    )


def main() -> int:
    """Fill session mappings if missing, then print classifications.

    Returns:
        Process exit code.

    Side Effects:
        May copy ``WORKER_SUPABASE_DB_URL`` onto checkpoint/LightRAG keys
        in gitignored ``.env.compose``. Never prints credentials.
    """

    compose_path = REPO / ".env.compose"
    if not compose_path.exists():
        print("env_compose_exists=false")
        return 1
    env = _parse_env(compose_path)
    worker = env.get("WORKER_SUPABASE_DB_URL", "").strip()
    if worker:
        if not env.get("LANGGRAPH_CHECKPOINT_URL", "").strip():
            _upsert_env(compose_path, "LANGGRAPH_CHECKPOINT_URL", worker)
            print("filled=LANGGRAPH_CHECKPOINT_URL_from_worker_session")
        if not env.get("LIGHTRAG_DB_URL", "").strip():
            _upsert_env(compose_path, "LIGHTRAG_DB_URL", worker)
            print("filled=LIGHTRAG_DB_URL_from_worker_session")
        env = _parse_env(compose_path)
    missing = [name for name in REQUIRED if not env.get(name, "").strip()]
    print("env_compose_exists=true")
    print("missing=" + (",".join(missing) if missing else "none"))
    for name in (
        "SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_URL",
        "API_SUPABASE_DB_URL",
        "WORKER_SUPABASE_DB_URL",
        "LANGGRAPH_CHECKPOINT_URL",
        "LIGHTRAG_DB_URL",
    ):
        print(_classify(name, env.get(name, "").strip()))
    anon = env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip()
    print(f"NEXT_PUBLIC_SUPABASE_ANON_KEY present={bool(anon)} length={len(anon)}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
