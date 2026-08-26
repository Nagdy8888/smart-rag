"""Import-boundary enforcement helpers for the Smart RAG monorepo.

These helpers scan Python source for forbidden cross-package imports. They are
pure static checks and do not execute application code.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

_SKIP_WALK_DIRS = frozenset({".venv", "node_modules", "__pycache__"})

FORBIDDEN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "packages/core/src",
        ("smart_rag_api", "smart_rag_worker", "smart_rag_agents", "apps."),
    ),
    ("apps/agents/src", ("smart_rag_api", "smart_rag_worker", "fastapi")),
    ("apps/worker/src", ("smart_rag_api", "fastapi")),
    ("apps/backend/src", ()),
)


@dataclass(frozen=True)
class BoundaryViolation:
    """A single forbidden import finding.

    Attributes:
        path: File containing the import.
        module: Imported module name.
        rule_root: Source tree root that owns the rule.
        line: 1-based line number of the import.
    """

    path: Path
    module: str
    rule_root: str
    line: int


@dataclass(frozen=True)
class ArtifactCountViolation:
    """Describe a missing, duplicate, or misplaced unique workspace artifact.

    Attributes:
        name: Artifact filename.
        expected: Required repository-relative location.
        discovered: Sorted repository-relative paths that were found.
    """

    name: str
    expected: str
    discovered: tuple[str, ...]


def scan_unique_workspace_artifacts(
    repo_root: Path,
) -> list[ArtifactCountViolation]:
    """Check the one-lockfile and one-LangGraph-project invariant.

    Args:
        repo_root: Repository root to inspect.

    Returns:
        Missing, duplicate, or misplaced artifact findings.
    """

    expectations = {
        "uv.lock": "uv.lock",
        "pnpm-lock.yaml": "pnpm-lock.yaml",
        "langgraph.json": "apps/agents/langgraph.json",
    }
    violations: list[ArtifactCountViolation] = []
    for name, expected in expectations.items():
        discovered = tuple(
            sorted(
                path.relative_to(repo_root).as_posix()
                for path in _iter_named_files(repo_root, name)
            )
        )
        if discovered != (expected,):
            violations.append(
                ArtifactCountViolation(
                    name=name,
                    expected=expected,
                    discovered=discovered,
                )
            )
    return violations


def _iter_named_files(root: Path, name: str) -> list[Path]:
    """Return files named ``name`` while pruning vendor trees.

    Args:
        root: Directory to walk.
        name: Exact filename to collect.

    Returns:
        Matching paths. ``node_modules`` is never entered so Windows
        junctions cannot abort the walk.
    """

    found: list[Path] = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [item for item in dirnames if item not in _SKIP_WALK_DIRS]
        if name in filenames:
            found.append(Path(current) / name)
    return found


def _iter_python_files(root: Path) -> list[Path]:
    """Return authored Python files under ``root``, excluding caches.

    Args:
        root: Directory to walk.

    Returns:
        Sorted list of ``.py`` files.
    """

    if not root.exists():
        return []
    files: list[Path] = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [item for item in dirnames if item not in _SKIP_WALK_DIRS]
        current_path = Path(current)
        for filename in filenames:
            if filename.endswith(".py"):
                files.append(current_path / filename)
    return sorted(files)


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """Extract imported module names and line numbers from an AST.

    Args:
        tree: Parsed module AST.

    Returns:
        List of ``(module_name, lineno)`` pairs.
    """

    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append((node.module, node.lineno))
    return found


def scan_tree_for_forbidden_imports(
    repo_root: Path,
    tree_relative: str,
    forbidden_prefixes: tuple[str, ...],
) -> list[BoundaryViolation]:
    """Scan one source tree for imports matching forbidden prefixes.

    Args:
        repo_root: Repository root path.
        tree_relative: Source tree relative to ``repo_root``.
        forbidden_prefixes: Module prefixes that must not appear.

    Returns:
        List of violations (empty when clean).
    """

    violations: list[BoundaryViolation] = []
    root = repo_root / tree_relative
    for path in _iter_python_files(root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for module, lineno in _imported_modules(tree):
            if any(
                module == prefix
                or module.startswith(f"{prefix}.")
                or module.startswith(prefix)
                for prefix in forbidden_prefixes
                if prefix
            ):
                # Distinguish exact package names from dotted prefixes carefully.
                matched = False
                for prefix in forbidden_prefixes:
                    if not prefix:
                        continue
                    if prefix.endswith("."):
                        matched = module.startswith(prefix)
                    else:
                        matched = module == prefix or module.startswith(f"{prefix}.")
                    if matched:
                        break
                if matched:
                    violations.append(
                        BoundaryViolation(
                            path=path,
                            module=module,
                            rule_root=tree_relative,
                            line=lineno,
                        )
                    )
    return violations


def scan_repository_boundaries(repo_root: Path) -> list[BoundaryViolation]:
    """Scan all configured package trees for forbidden import directions.

    Args:
        repo_root: Repository root containing ``apps/`` and ``packages/``.

    Returns:
        Aggregated list of boundary violations.
    """

    findings: list[BoundaryViolation] = []
    for tree_relative, forbidden in FORBIDDEN_RULES:
        findings.extend(
            scan_tree_for_forbidden_imports(repo_root, tree_relative, forbidden)
        )
    return findings


def assert_frontend_has_no_python_workspace_imports(repo_root: Path) -> list[str]:
    """Detect frontend references to Python workspace import paths.

    Args:
        repo_root: Repository root.

    Returns:
        List of offending file paths as strings.
    """

    frontend = repo_root / "apps" / "frontend"
    if not frontend.exists():
        return []
    offenders: list[str] = []
    needles = (
        "smart_rag_core",
        "smart_rag_agents",
        "smart_rag_api",
        "smart_rag_worker",
        "packages/core",
        "apps/agents",
        "apps/backend",
        "apps/worker",
    )
    skip_dirs = _SKIP_WALK_DIRS | {".next"}
    for current, dirnames, filenames in os.walk(frontend, followlinks=False):
        dirnames[:] = [item for item in dirnames if item not in skip_dirs]
        current_path = Path(current)
        for filename in filenames:
            path = current_path / filename
            if path.suffix.lower() not in {
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                ".mjs",
                ".cjs",
            }:
                continue
            text = path.read_text(encoding="utf-8")
            if any(needle in text for needle in needles):
                offenders.append(str(path.relative_to(repo_root)))
    return offenders
