"""Copy public frontend Auth keys for laptop ask against hosted Supabase."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ENV = REPO_ROOT / "apps" / "frontend" / ".env.local"
PUBLIC_KEYS = (
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
)


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to values.
    """

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


def _upsert(path: Path, updates: dict[str, str]) -> None:
    """Insert or replace keys without rewriting unrelated lines.

    Args:
        path: Frontend env file.
        updates: Public keys only.
    """

    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    found: set[str] = set()
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing = stripped.split("=", 1)[0].strip()
            if existing in updates:
                out.append(f"{existing}={updates[existing]}")
                found.add(existing)
                continue
        out.append(raw)
    for key, value in updates.items():
        if key not in found:
            out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    """Write hosted public Auth keys and laptop API origin.

    Returns:
        Process exit code.

    Side Effects:
        Updates gitignored ``apps/frontend/.env.local``. Does not print values.
    """

    root_env = _parse_env(REPO_ROOT / ".env")
    updates = {"NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8000"}
    for key in PUBLIC_KEYS:
        value = root_env.get(key, "").strip()
        if not value:
            print(f"missing_{key}")
            return 1
        if key == "NEXT_PUBLIC_SUPABASE_URL" and "supabase.co" not in value:
            print("frontend_supabase_url_not_hosted")
            return 1
        updates[key] = value
    _upsert(FRONTEND_ENV, updates)
    print("wrote=apps/frontend/.env.local")
    print("NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000")
    print("NEXT_PUBLIC_SUPABASE_URL=hosted")
    print("NEXT_PUBLIC_SUPABASE_ANON_KEY=present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
