#!/usr/bin/env python3
"""Verify unique frontend action IDs match the shipped inventory.

The checker reads ``docs/frontend/action-inventory.json`` and scans
``apps/frontend/src`` for ``data-action-id`` literals, template prefixes,
and ``actionId`` properties. It does not use an all-buttons regex.

Keep actions must name an existing test file. Removed-target IDs must not
appear in production source. Local-state actions are first-class inventory
rows.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "docs" / "frontend" / "action-inventory.json"
FRONTEND_SRC = REPO_ROOT / "apps" / "frontend" / "src"
FRONTEND_ROOT = REPO_ROOT / "apps" / "frontend"

STATIC_ACTION_ID = re.compile(r'data-action-id=(["\'])([^"\']+)\1')
TEMPLATE_PREFIX = re.compile(r"data-action-id=\{`([^`$]+)\$\{")
ACTION_ID_PROP = re.compile(r'actionId:\s*["\']([^"\']+)["\']')
SOURCE_SUFFIXES = {".ts", ".tsx"}
PLACEHOLDER_TEST_PREFIXES = ("pending-",)
NON_KEEP_TEST_PREFIXES = ("removed-", "retired-", "redirect-")


def _iter_source_files() -> list[Path]:
    """Return production TypeScript files under the frontend src tree.

    Returns:
        Files excluding tests, snapshots, and generated Next artifacts.
    """

    found: list[Path] = []
    for path in FRONTEND_SRC.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        name = path.name
        if name.endswith(".test.ts") or name.endswith(".test.tsx"):
            continue
        if ".next" in path.parts or "node_modules" in path.parts:
            continue
        found.append(path)
    return found


def collect_source_actions() -> tuple[set[str], set[str]]:
    """Collect exact action IDs and template prefixes from source.

    Returns:
        Tuple of exact IDs and template prefixes such as ``admin.tab.``.
    """

    exact: set[str] = set()
    prefixes: set[str] = set()
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        exact.update(match.group(2) for match in STATIC_ACTION_ID.finditer(text))
        exact.update(match.group(1) for match in ACTION_ID_PROP.finditer(text))
        prefixes.update(match.group(1) for match in TEMPLATE_PREFIX.finditer(text))
    return exact, prefixes


def resolve_test_file(test_id: str) -> Path | None:
    """Resolve an inventory ``test_id`` to an existing file.

    Args:
        test_id: Inventory test identifier, usually a path under the frontend.

    Returns:
        Existing path, or None when the id is a non-keep marker or missing.
    """

    if test_id.startswith(NON_KEEP_TEST_PREFIXES) or test_id.startswith(
        PLACEHOLDER_TEST_PREFIXES
    ):
        return None
    candidates = (
        FRONTEND_ROOT / test_id,
        FRONTEND_SRC / test_id,
        FRONTEND_SRC / "components" / test_id,
        FRONTEND_SRC / "lib" / test_id,
        FRONTEND_ROOT / "tests" / "e2e" / test_id,
        REPO_ROOT / test_id,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def source_covers(action_id: str, exact: set[str], prefixes: set[str]) -> bool:
    """Return whether production source references an inventory action.

    Args:
        action_id: Inventory action id.
        exact: Literal IDs found in source.
        prefixes: Template prefixes found in source.

    Returns:
        True when the id is a literal or matches a template prefix.
    """

    if action_id in exact:
        return True
    return any(action_id.startswith(prefix) for prefix in prefixes)


def check_inventory() -> list[str]:
    """Validate uniqueness, keep coverage, and removed-target absence.

    Returns:
        Human-readable failure strings. Empty means the inventory is sound.
    """

    failures: list[str] = []
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return ["action-inventory.json missing actions array"]

    ids: list[str] = []
    by_id: dict[str, dict[str, object]] = {}
    for raw in actions:
        if not isinstance(raw, dict):
            failures.append("inventory row is not an object")
            continue
        action_id = raw.get("action_id")
        if not isinstance(action_id, str) or action_id == "":
            failures.append("inventory row missing action_id")
            continue
        ids.append(action_id)
        by_id[action_id] = raw

    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        failures.append(f"duplicate action_id values: {duplicates}")

    exact, prefixes = collect_source_actions()

    for action_id, row in by_id.items():
        disposition = str(row.get("disposition", ""))
        test_id = str(row.get("test_id", ""))
        control_kind = str(row.get("control_kind", ""))
        failure_state = str(row.get("failure_state", ""))
        if test_id.startswith(PLACEHOLDER_TEST_PREFIXES):
            failures.append(f"{action_id}: placeholder test_id {test_id}")
        if disposition == "keep":
            resolved = resolve_test_file(test_id)
            if resolved is None:
                failures.append(f"{action_id}: keep test_id not found ({test_id})")
            if not source_covers(action_id, exact, prefixes):
                failures.append(f"{action_id}: keep action missing from source")
            if control_kind != "local-state" and failure_state in {"", "n/a"}:
                failures.append(f"{action_id}: keep action missing failure_state")
        if disposition == "removed_target" and source_covers(
            action_id, exact, prefixes
        ):
            failures.append(f"{action_id}: removed_target still present in source")

    for source_id in sorted(exact):
        if source_id not in by_id:
            failures.append(f"unmapped source data-action-id: {source_id}")

    for prefix in sorted(prefixes):
        if not any(
            action_id.startswith(prefix) and str(row.get("disposition")) == "keep"
            for action_id, row in by_id.items()
        ):
            failures.append(f"template prefix {prefix} has no keep inventory rows")

    return failures


def main() -> int:
    """Run the inventory check and print failures.

    Returns:
        ``0`` when the inventory matches source. ``1`` on any failure.
    """

    failures = check_inventory()
    if failures:
        print("Frontend action inventory failed:", file=sys.stderr)
        for item in failures:
            print(f"- {item}", file=sys.stderr)
        return 1
    print("Frontend action inventory verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
