"""AST enforcement helpers for authored Python docstrings."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

_EXCLUDED_PARTS = {
    ".private-eval",
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


def _is_excluded(path: Path) -> bool:
    """Return whether a path is cache, vendor, or local scratch output.

    Args:
        path: Candidate Python file.

    Returns:
        True when the file must not participate in authored-code contracts.
    """

    if any(part in _EXCLUDED_PARTS for part in path.parts):
        return True
    return any(
        part.startswith(".tmp") or part.startswith("_tmp")
        for part in (*path.parts, path.name)
    )


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
        Python source paths excluding caches, build output, historical review
        artifacts, vendor directories, and local ``.tmp*`` / ``_tmp*``
        scratch files.
        Excluded directory names are pruned during ``os.walk`` so Windows
        ``node_modules`` junctions cannot raise ``FileNotFoundError``.
    """

    found: list[Path] = []
    # Imported tools are checksum-pinned upstream code, not application Python.
    # Keep custom project skills and identically named application modules covered.
    vendored_skill_roots = {
        repo_root / ".agents" / "skills" / name
        for name in ("security-audit", "skill-creator", "ui-ux-pro-max")
    }
    for current, dirnames, filenames in os.walk(repo_root, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if (
                name not in _EXCLUDED_PARTS
                and Path(current) / name not in vendored_skill_roots
                and not name.startswith(".tmp")
                and not name.startswith("_tmp")
            )
        ]
        current_path = Path(current)
        if _is_excluded(current_path):
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = current_path / filename
            if not _is_excluded(path):
                found.append(path)
    return sorted(found)


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
