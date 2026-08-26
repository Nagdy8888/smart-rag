"""Contract tests for safe local lifecycle and verification scripts."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _script_text(name: str) -> str:
    """Read one PowerShell lifecycle script as normalized source text.

    Args:
        name: Script filename under the repository ``scripts`` directory.

    Returns:
        UTF-8 script source with forward slashes preserved as authored.
    """

    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_lifecycle_scripts_share_compose_environment_precedence() -> None:
    """Start, stop, reset, and verification prefer the same environment files."""

    assert r"$Root\.env.compose" in _script_text("dev.ps1")
    for name in ("stop.ps1", "reset.ps1", "verify-local.ps1"):
        source = _script_text(name)
        compose_index = source.index(r"$Root\.env.compose")
        local_index = source.index(r'$Root\.env"')
        assert compose_index < local_index, f"{name} must prefer .env.compose"

    assert r"$Root\node_modules\.bin\supabase.cmd" in _script_text("reset.ps1")
    assert "pnpm exec supabase" in _script_text("reset.ps1")
    assert "pnpm exec supabase" not in _script_text("dev.ps1")
    assert "pnpm exec supabase" not in _script_text("stop.ps1")
    assert "ensure_app_runtime_role.py" not in _script_text("dev.ps1")

    assert "docker compose --env-file $EnvFile stop" in _script_text("stop.ps1")
    assert "docker compose --env-file $EnvFile down -v" in _script_text("reset.ps1")
    assert "docker compose --env-file $EnvFile up" in _script_text("dev.ps1")

    reset_source = _script_text("reset.ps1")
    ensure_index = reset_source.index("ensure_app_runtime_role.py")
    reset_index = reset_source.index("pnpm exec supabase db reset")
    assert reset_index < ensure_index


def test_dev_startup_is_hosted_runtime_only() -> None:
    """Daily startup requires hosted Compose names and never starts local Auth."""

    source = _script_text("dev.ps1")
    assert "wire_hosted_ingest_env.py" in source
    assert "SUPABASE_URL" in source
    assert "API_SUPABASE_DB_URL" in source
    assert "WORKER_SUPABASE_DB_URL" in source
    assert "LANGGRAPH_CHECKPOINT_URL" in source
    assert "NEXT_PUBLIC_SUPABASE_URL" in source
    assert "supabase start" not in source
    bash = (SCRIPTS / "dev.sh").read_text(encoding="utf-8")
    assert "supabase start" not in bash
    assert "wire_hosted_ingest_env.py" in bash


def test_local_supabase_fixture_script_is_explicitly_named() -> None:
    """Local Supabase start remains reachable only as a CI/fixture command."""

    source = (SCRIPTS / "ci" / "start_local_supabase_fixture.ps1").read_text(
        encoding="utf-8"
    )
    assert "pnpm exec supabase start" in source
    assert "ensure_app_runtime_role.py" in source
    assert "destructive" in source.casefold() or "fixture" in source.casefold()


def test_reset_requires_confirmation_before_destructive_compose_call() -> None:
    """The destructive reset must fail closed before removing local volumes."""

    source = _script_text("reset.ps1")
    refusal_index = source.index("if (-not $ConfirmReset)")
    destructive_index = source.index("docker compose --env-file $EnvFile down -v")
    assert refusal_index < destructive_index
    assert "exit 2" in source[refusal_index:destructive_index]


def test_local_verification_covers_private_service_invariants() -> None:
    """Runtime verification must fail on missing or weakened private services."""

    source = _script_text("verify-local.ps1")
    required_fragments = (
        'throw "Required private service missing from Compose: $name"',
        '"valkey-limits"',
        '"noeviction"',
        '"valkey-cache"',
        '"allkeys-lru"',
        "accepted an unauthenticated ping",
        '@("api", "worker", "frontend")',
        "MOCK_MODEL_MODE=true",
        "OPENAI_API_KEY",
    )
    for fragment in required_fragments:
        assert fragment in source
