"""Contract tests for monorepo import boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.boundary_scanner import (
    assert_frontend_has_no_python_workspace_imports,
    scan_repository_boundaries,
    scan_tree_for_forbidden_imports,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_workspace_source_trees_have_no_forbidden_imports() -> None:
    """Production source trees must satisfy Section 3 dependency directions."""

    violations = scan_repository_boundaries(REPO_ROOT)
    assert violations == [], (
        "Forbidden imports detected:\n"
        + "\n".join(
            f"{item.path}:{item.line} imports {item.module} (rule {item.rule_root})"
            for item in violations
        )
    )


def test_frontend_does_not_import_python_workspace_paths() -> None:
    """Frontend may use HTTP/Supabase only; no Python package path imports."""

    offenders = assert_frontend_has_no_python_workspace_imports(REPO_ROOT)
    assert offenders == [], f"Frontend Python workspace references: {offenders}"


def test_boundary_scanner_fails_on_intentional_negative_fixture(
    tmp_path: Path,
) -> None:
    """Prove the checker detects a forbidden core→backend import."""

    core_src = tmp_path / "packages" / "core" / "src" / "smart_rag_core"
    core_src.mkdir(parents=True)
    bad = core_src / "bad_import.py"
    bad.write_text(
        '"""Intentional boundary violation fixture."""\n'
        "from smart_rag_api.main import app\n",
        encoding="utf-8",
    )
    violations = scan_tree_for_forbidden_imports(
        tmp_path,
        "packages/core/src",
        ("smart_rag_api", "smart_rag_worker", "smart_rag_agents", "apps."),
    )
    assert len(violations) == 1
    assert violations[0].module == "smart_rag_api.main"


def test_exactly_one_langgraph_json_and_lockfiles() -> None:
    """Repository must contain exactly one LangGraph project and one lockfile each."""

    langgraph_files = list(REPO_ROOT.rglob("langgraph.json"))
    langgraph_files = [
        path
        for path in langgraph_files
        if ".venv" not in path.parts and "node_modules" not in path.parts
    ]
    assert len(langgraph_files) == 1
    assert langgraph_files[0] == REPO_ROOT / "apps" / "agents" / "langgraph.json"

    uv_locks = [
        path
        for path in REPO_ROOT.rglob("uv.lock")
        if ".venv" not in path.parts
    ]
    pnpm_locks = [
        path
        for path in REPO_ROOT.rglob("pnpm-lock.yaml")
        if "node_modules" not in path.parts
    ]
    assert len(uv_locks) == 1
    assert uv_locks[0] == REPO_ROOT / "uv.lock"
    assert len(pnpm_locks) == 1
    assert pnpm_locks[0] == REPO_ROOT / "pnpm-lock.yaml"


@pytest.mark.parametrize(
    ("distribution", "import_name"),
    [
        ("smart-rag-core", "smart_rag_core"),
        ("smart-rag-agents", "smart_rag_agents"),
        ("smart-rag-backend", "smart_rag_api"),
        ("smart-rag-worker", "smart_rag_worker"),
    ],
)
def test_distribution_import_names(distribution: str, import_name: str) -> None:
    """Distribution names resolve to the planned import packages."""

    module = __import__(import_name)
    assert module.__name__ == import_name
    assert hasattr(module, "__version__")
