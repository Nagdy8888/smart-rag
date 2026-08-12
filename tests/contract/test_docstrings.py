"""Contract tests for AST-based Python docstring enforcement."""

from __future__ import annotations

from pathlib import Path

from tests.contract.docstring_scanner import (
    scan_repository_docstrings,
    scan_source_for_docstrings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
NEGATIVE_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "docstrings" / "missing_docstring.py.fixture"
)


def test_all_authored_python_definitions_have_docstrings() -> None:
    """Every authored module, class, function, async function, and method is documented."""

    violations = scan_repository_docstrings(REPO_ROOT)
    assert violations == [], "\n".join(
        f"{item.path}:{item.line} missing {item.kind} docstring for {item.name}"
        for item in violations
    )


def test_docstring_scanner_rejects_intentional_negative_fixture() -> None:
    """The checker must detect the intentionally undocumented fixture function."""

    violations = scan_source_for_docstrings(
        NEGATIVE_FIXTURE.read_text(encoding="utf-8"),
        NEGATIVE_FIXTURE,
    )
    assert len(violations) == 1
    assert violations[0].name == "undocumented_function"
