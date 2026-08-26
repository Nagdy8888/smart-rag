"""v1 prohibited retrieval methods. Extension points exist; runtimes do not."""

from __future__ import annotations

import re
from pathlib import Path

PROHIBITED_DEPENDENCY_NAMES: tuple[str, ...] = (
    "colbert",
    "colbert-ai",
    "flashrank",
    "haystack-ai",
    "llama-index-packs-raptor",
    "ragatouille",
    "raptor",
    "rerankers",
    "sentence-transformers",
    "splade",
)

PROHIBITED_IMPORT_NAMES: tuple[str, ...] = (
    "colbert",
    "flashrank",
    "hyde",
    "ragatouille",
    "raptor",
    "sentence_transformers",
    "splade",
)

PROHIBITED_LOCK_PACKAGES: tuple[str, ...] = (
    "colbert",
    "colbert-ai",
    "flashrank",
    "haystack-ai",
    "llama-index-packs-raptor",
    "ragatouille",
    "raptor",
    "rerankers",
    "sentence-transformers",
    "splade",
    "transformers",
)


class ProhibitedMethodError(RuntimeError):
    """A forbidden v1 retrieval method or dependency was detected."""


def _lock_package_declared(lock_text: str, name: str) -> bool:
    """Return whether ``uv.lock`` declares one distribution name.

    Args:
        lock_text: ``uv.lock`` contents.
        name: Exact distribution name.

    Returns:
        True when a ``name = "..."`` stanza matches.
    """

    pattern = r'(?im)^name = "' + re.escape(name) + r'"$'
    return re.search(pattern, lock_text) is not None


def scan_lockfile(lock_text: str) -> tuple[str, ...]:
    """Return prohibited distribution names declared in a lockfile.

    Args:
        lock_text: ``uv.lock`` contents.

    Returns:
        Sorted unique package names present as lock ``name`` stanzas.
    """

    return tuple(
        name
        for name in PROHIBITED_LOCK_PACKAGES
        if _lock_package_declared(lock_text, name)
    )


_SKIP_PYPROJECT_DIR_NAMES: frozenset[str] = frozenset(
    {".git", ".venv", "node_modules", "__pycache__"}
)


def _iter_workspace_pyprojects(root: Path) -> tuple[Path, ...]:
    """Yield workspace ``pyproject.toml`` files, skipping vendor trees.

    Recursive glob from the repository root follows ``node_modules/.pnpm``
    junctions on Windows and can raise ``FileNotFoundError`` when a store
    path is missing. Workspace members live beside, not inside, those trees.

    Args:
        root: Repository root.

    Returns:
        Existing pyproject paths under the workspace, excluding skipped dirs.
    """

    found: list[Path] = []
    top = root / "pyproject.toml"
    if top.is_file():
        found.append(top)
    for child in root.iterdir():
        if not child.is_dir() or child.name in _SKIP_PYPROJECT_DIR_NAMES:
            continue
        for path in child.rglob("pyproject.toml"):
            if any(part in _SKIP_PYPROJECT_DIR_NAMES for part in path.parts):
                continue
            found.append(path)
    return tuple(found)


def scan_pyproject_files(root: Path) -> tuple[str, ...]:
    """Return prohibited distribution names found in workspace pyproject files.

    Bare ``transformers`` is intentionally omitted here because it matches
    unrelated comments. The lockfile scan still rejects that distribution.

    Args:
        root: Repository root.

    Returns:
        Sorted unique prohibited names found in any workspace
        ``pyproject.toml``. Vendor trees such as ``node_modules`` are skipped.
    """

    found: set[str] = set()
    for path in _iter_workspace_pyprojects(root):
        text = path.read_text(encoding="utf-8").lower()
        for name in PROHIBITED_DEPENDENCY_NAMES:
            pattern = r"(?<![a-z0-9_-])" + re.escape(name) + r"(?![a-z0-9_-])"
            if re.search(pattern, text):
                found.add(name)
    return tuple(sorted(found))
