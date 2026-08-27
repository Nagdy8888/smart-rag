"""Unit tests for the local ``app_runtime`` LOGIN wrapper helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "ensure_app_runtime_role.py"


def _load_module():
    """Load the operator script as a module.

    Returns:
        Loaded module exposing env parse/upsert helpers.

    Raises:
        AssertionError: If the script path cannot be imported.
    """

    spec = importlib.util.spec_from_file_location("ensure_app_runtime_role", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_env_example_defines_compose_runtime_password() -> None:
    """``.env.example`` must interpolate Compose without a missing-var error.

    Required Compose names stay uncommented with non-superuser placeholders
    so ``docker compose --env-file .env.example config`` succeeds in CI.
    """

    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "APP_RUNTIME_DB_PASSWORD=" in text
    assert "change-me-app-runtime" in text
    assignments = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in text.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    for key in (
        "API_SUPABASE_DB_URL",
        "WORKER_SUPABASE_DB_URL",
        "LANGGRAPH_CHECKPOINT_URL",
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ):
        assert assignments[key]
        assert "postgresql://postgres:" not in assignments[key]
        assert "host.docker.internal" not in assignments[key]


def test_upsert_env_inserts_and_replaces_without_clobbering_comments(
    tmp_path: Path,
) -> None:
    """Existing keys are replaced; comments and other keys stay intact."""

    module = _load_module()
    path = tmp_path / ".env"
    path.write_text(
        "# keep me\nOTHER=1\nAPP_RUNTIME_DB_PASSWORD=old\n",
        encoding="utf-8",
    )
    replacement = "rotated-wrapper"
    module._upsert_env(path, module.RUNTIME_WRAPPER_ENV, replacement)
    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert "OTHER=1" in text
    assert f"{module.RUNTIME_WRAPPER_ENV}={replacement}" in text
    assert f"{module.RUNTIME_WRAPPER_ENV}=old" not in text
    parsed = module._parse_env(path)
    assert parsed["OTHER"] == "1"
    assert parsed[module.RUNTIME_WRAPPER_ENV] == replacement
