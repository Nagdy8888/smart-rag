"""AST enforcement helpers for authored Python docstrings."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "prev_review",
    "vendor",
}


@dataclass(frozen=True)
class DocstringViolation:
    """Describe one authored definition missing a docstring.

    Attributes:
        path: File containing the missing documentation.
        line: One-based source line.
        kind: Module, class, function, async function, or method kind.
        name: Definition name.
    """

    path: Path
    line: int
    kind: str
    name: str


def iter_authored_python_files(repo_root: Path) -> list[Path]:
    """Return every authored Python file in stable path order.

    Args:
        repo_root: Repository root to inspect.

    Returns:
        Python source paths excluding only caches, build output, historical
        review artifacts, and explicit vendor directories.
    """

    return sorted(
        path
        for path in repo_root.rglob("*.py")
        if not any(part in _EXCLUDED_PARTS for part in path.parts)
    )


def scan_source_for_docstrings(source: str, path: Path) -> list[DocstringViolation]:
    """Scan one Python source string for required AST docstrings.

    Args:
        source: Python source text.
        path: Display path associated with the source.

    Returns:
        Missing module, class, function, async-function, and method docstrings.

    Raises:
        SyntaxError: If ``source`` is not valid Python.
    """

    tree = ast.parse(source, filename=str(path))
    violations: list[DocstringViolation] = []
    if ast.get_docstring(tree, clean=False) is None:
        violations.append(DocstringViolation(path, 1, "module", path.stem))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            kind = "class"
        elif isinstance(node, ast.AsyncFunctionDef):
            kind = "async function"
        elif isinstance(node, ast.FunctionDef):
            kind = "function"
        else:
            continue
        if ast.get_docstring(node, clean=False) is None:
            violations.append(DocstringViolation(path, node.lineno, kind, node.name))
    return violations


def scan_repository_docstrings(repo_root: Path) -> list[DocstringViolation]:
    """Scan every authored Python definition in the repository.

    Args:
        repo_root: Repository root to inspect.

    Returns:
        Aggregated missing-docstring findings.
    """

    findings: list[DocstringViolation] = []
    for path in iter_authored_python_files(repo_root):
        findings.extend(
            scan_source_for_docstrings(path.read_text(encoding="utf-8"), path)
        )
    return findings
