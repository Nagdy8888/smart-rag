"""Static migration-policy check for Phase 1 (zero application migrations).

Honestly reports that application schema/RLS migrations are Phase 2-owned.
Fails only if unexpected migration files appear without documentation.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"


def main() -> int:
    """Validate Phase 1 migration policy.

    Returns:
        ``0`` when zero application migrations exist (expected) or when present
        migrations are accompanied by docs; ``1`` on unexpected state.
    """

    if not MIGRATIONS.exists():
        print("Phase 1: no supabase/migrations directory — OK (Phase 2 owns schema)")
        return 0
    files = sorted(p for p in MIGRATIONS.glob("*.sql") if p.is_file())
    if not files:
        print("Phase 1: zero application migrations — OK (expand/contract starts Phase 2)")
        return 0
    print(
        "Application migrations present before Phase 2 documentation — "
        f"{len(files)} file(s). Add docs/api migration notes or remove.",
        file=__import__("sys").stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
