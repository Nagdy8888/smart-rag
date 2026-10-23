"""Contract tests for AST-based Python docstring enforcement."""

from __future__ import annotations

from pathlib import Path

from tests.contract.docstring_scanner import (
    iter_authored_python_files,
    scan_repository_docstrings,
    scan_source_for_docstrings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NEGATIVE_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "docstrings" / "missing_docstring.py.fixture"
)


def test_iter_authored_python_files_skips_node_modules(tmp_path: Path) -> None:
    """Vendor trees are pruned before walk so Windows junctions cannot abort."""

    authored = tmp_path / "packages" / "core" / "mod.py"
    authored.parent.mkdir(parents=True)
    authored.write_text('"""Authored module."""\n', encoding="utf-8")
    vendor = tmp_path / "node_modules" / "undici" / "vendor.py"
    vendor.parent.mkdir(parents=True)
    vendor.write_text("VALUE = 1\n", encoding="utf-8")

    found = iter_authored_python_files(tmp_path)

    assert authored in found
    assert vendor not in found


def test_all_authored_python_definitions_have_docstrings() -> None:
    """Every authored module, class, function, async function, and method is documented."""

    violations = scan_repository_docstrings(REPO_ROOT)
    assert violations == [], "\n".join(
        f"{item.path}:{item.line} missing {item.kind} docstring for {item.name}"
        for item in violations
    )


def test_imported_skill_tools_are_not_application_authored_code(tmp_path: Path) -> None:
    """Exclude only imported tool roots while retaining custom skills and app code."""
    imported = [
        tmp_path / ".agents" / "skills" / name / "tool.py"
        for name in ("security-audit", "skill-creator", "ui-ux-pro-max")
    ]
    authored = [
        tmp_path / ".agents" / "skills" / "project-helper" / "tool.py",
        tmp_path / "apps" / "skill-creator" / "tool.py",
    ]
    for path in (*imported, *authored):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE = 1\n", encoding="utf8")
    assert iter_authored_python_files(tmp_path) == sorted(authored)
    assert {v.path for v in scan_repository_docstrings(tmp_path)} == set(authored)


def test_docstring_scanner_rejects_intentional_negative_fixture() -> None:
    """The checker must detect the intentionally undocumented fixture function."""

    violations = scan_source_for_docstrings(
        NEGATIVE_FIXTURE.read_text(encoding="utf-8"),
        NEGATIVE_FIXTURE,
    )
    assert len(violations) == 1
    assert violations[0].name == "undocumented_function"
