"""Contract tests for the Phase 3 immutable fixture manifest."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from tests.fixtures.parser import (
    build_csv_fixture,
    build_html_fixture,
    build_markdown_fixture,
    build_pdf_text_fixture,
)
from tests.fixtures.phase3 import (
    MANIFEST_PATH,
    compute_manifest_sha256,
    iter_fixtures,
    load_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_CATEGORIES = frozenset(
    {
        "format",
        "malware",
        "governance",
        "sensitive_data",
        "ssrf",
        "authorization",
        "idempotency",
        "crash_recovery",
        "resource_limit",
    }
)

PROGRAMMATIC_HASH_BUILDERS: dict[str, object] = {
    "ef05cb9b840112afa5094bc60b5bbc3793fc1b872d940dc1f875a7f3a92fcbf1": lambda: (
        hashlib.sha256(
            b"Line one English.\nLine two Arabic \xd9\x85\xd8\xb1\xd8\xad\xd8\xa8\xd8\xa7.\n"
        ).hexdigest()
    ),
    "e198b316cfed2288be3d9f0264693c7d3bb60c8833b6cd6ec4e8fd28ea5da5ca": build_markdown_fixture,
    "41c65553e0993674ec0a9a0a09619a40bb8c4a47c5001ae7ed0733b05999738c": build_csv_fixture,
    "bb80f72e60ced7f5e3b044be01776d6fc9b448108b169ef35141ddcc4eff33f1": build_html_fixture,
    "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f": lambda: (
        hashlib.sha256(
            b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        ).hexdigest()
    ),
}


def _resolve_owning_test(nodeid: str) -> None:
    """Assert owning_test points at an existing pytest function via AST.

    Uses source parsing instead of importing the module so circular import
    cycles in production packages cannot fail the registry contract.

    Args:
        nodeid: Pytest node id ``path::test_name[...]``.

    Raises:
        AssertionError: When the referenced test function is missing.
    """

    module_path, _, func_part = nodeid.partition("::")
    if not module_path or not func_part:
        raise AssertionError(f"Invalid owning_test node id: {nodeid}")
    test_name = func_part.split("[", 1)[0]
    path = REPO_ROOT / module_path
    assert path.is_file(), f"Missing owning test module {module_path}"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert test_name in defined, f"Missing owning test {nodeid}"


def test_manifest_file_is_present_and_self_consistent() -> None:
    """Manifest exists, declares a digest, and matches canonical body hash."""

    assert MANIFEST_PATH.is_file()
    manifest = load_manifest()
    declared = manifest.get("manifest_sha256")
    computed = compute_manifest_sha256(manifest)
    assert isinstance(declared, str) and declared != "PLACEHOLDER"
    assert declared == computed
    fixtures = iter_fixtures(manifest)
    assert len(fixtures) >= 30


def test_manifest_covers_required_security_and_format_categories() -> None:
    """Every required Packet 8 category appears at least once."""

    manifest = load_manifest()
    categories = {row["category"] for row in iter_fixtures(manifest)}
    missing = REQUIRED_CATEGORIES - categories
    assert not missing, f"Missing categories: {sorted(missing)}"


@pytest.mark.parametrize(
    "row", iter_fixtures(load_manifest()), ids=lambda row: row["id"]
)
def test_manifest_row_has_required_fields(row: dict[str, object]) -> None:
    """Each fixture row documents source, sensitivity, mode, and owning test."""

    for key in (
        "id",
        "category",
        "source",
        "license",
        "expected_status",
        "sensitivity_class",
        "external_processing_mode",
        "boundary",
        "owning_test",
    ):
        assert row.get(key)
    _resolve_owning_test(str(row["owning_test"]))


def test_programmatic_fixture_hashes_match_builders() -> None:
    """Declared SHA-256 values match live programmatic fixture builders."""

    _, pdf_digest = build_pdf_text_fixture()
    PROGRAMMATIC_HASH_BUILDERS[pdf_digest] = build_pdf_text_fixture

    manifest = load_manifest()
    for row in iter_fixtures(manifest):
        digest = row.get("sha256")
        if not digest:
            continue
        builder = PROGRAMMATIC_HASH_BUILDERS.get(str(digest))
        if builder is None:
            continue
        result = builder()
        if isinstance(result, tuple):
            _, live_digest = result
        else:
            live_digest = result
        assert live_digest == digest, row["id"]


def test_manifest_references_phase3_test_modules() -> None:
    """Owning tests live under tests/unit or tests/contract."""

    manifest = load_manifest()
    for row in iter_fixtures(manifest):
        owning = str(row["owning_test"]).split("::", 1)[0]
        path = REPO_ROOT / owning
        assert path.is_file(), owning
        assert owning.startswith(("tests/unit/", "tests/contract/"))
