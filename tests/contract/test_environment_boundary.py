"""Contract tests that centralize process environment access in settings."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contract.docstring_scanner import iter_authored_python_files

REPO_ROOT = Path(__file__).resolve().parents[2]


def _unauthorized_environment_reads(path: Path) -> list[int]:
    """Return environment-read line numbers outside the settings package.

    Args:
        path: Python source file to scan.

    Returns:
        One-based lines containing direct ``os.getenv`` or ``os.environ``
        access, including equivalent direct imports.
    """

    normalized = path.as_posix()
    if "/smart_rag_core/settings/" in normalized:
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    direct_names: set[str] = set()
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            direct_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in {"environ", "getenv"}
            )
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in {"environ", "getenv"}
        ):
            lines.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id in direct_names:
            lines.append(node.lineno)
    return sorted(set(lines))


def test_process_environment_reads_are_centralized() -> None:
    """No authored Python file reads environment outside core settings."""

    findings = {
        path.relative_to(REPO_ROOT): lines
        for path in iter_authored_python_files(REPO_ROOT)
        if (lines := _unauthorized_environment_reads(path))
    }
    assert findings == {}
