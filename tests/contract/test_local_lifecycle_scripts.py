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

    for name in ("dev.ps1", "stop.ps1", "reset.ps1", "verify-local.ps1"):
        source = _script_text(name)
        compose_index = source.index(r"$Root\.env.compose")
        local_index = source.index(r'$Root\.env"')
        assert compose_index < local_index, f"{name} must prefer .env.compose"

    for name in ("dev.ps1", "stop.ps1", "reset.ps1"):
        source = _script_text(name)
        assert r"$Root\node_modules\.bin\supabase.cmd" in source
        assert "pnpm exec supabase" in source

    assert "docker compose --env-file $EnvFile stop" in _script_text("stop.ps1")
    assert "docker compose --env-file $EnvFile down -v" in _script_text("reset.ps1")

    for name in ("dev.ps1", "reset.ps1"):
        source = _script_text(name)
        ensure_index = source.index("ensure_app_runtime_role.py")
        if name == "dev.ps1":
            supabase_index = source.index("pnpm exec supabase start")
            compose_index = source.index("docker compose --env-file $EnvFile up")
            assert supabase_index < ensure_index < compose_index
        else:
            reset_index = source.index("pnpm exec supabase db reset")
            assert reset_index < ensure_index


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
