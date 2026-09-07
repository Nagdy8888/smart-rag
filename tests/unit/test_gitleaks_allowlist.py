"""Gitleaks allowlists must cover Nightly full-history false positives."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[2]
GITLEAKS_TOML = REPO_ROOT / ".gitleaks.toml"


def _toml_object(value: object, *, label: str) -> dict[str, object]:
    """Return a string-keyed object from parsed TOML.

    Args:
        value: Candidate mapping from ``tomllib``.
        label: Field name used in the assertion message.

    Returns:
        The same mapping with a ``dict[str, object]`` type.

    Raises:
        AssertionError: If ``value`` is not a mapping.
    """

    assert isinstance(value, dict), f"{label} must be a TOML table"
    return cast(dict[str, object], value)


def _string_values(value: object) -> list[str]:
    """Return TOML array values as strings.

    Args:
        value: Candidate array from an allowlist table.

    Returns:
        Each array element, which must already be a string.
    """

    if not isinstance(value, list):
        return []
    items: list[str] = []
    for raw_item in cast(list[object], value):
        assert isinstance(raw_item, str)
        items.append(raw_item)
    return items


def _allowlists() -> list[dict[str, object]]:
    """Load ``[[allowlists]]`` tables from the committed Gitleaks config.

    Returns:
        Allowlist objects from ``.gitleaks.toml``.
    """

    parsed = _toml_object(
        tomllib.loads(GITLEAKS_TOML.read_text(encoding="utf-8")),
        label="gitleaks root",
    )
    tables = parsed.get("allowlists")
    if not isinstance(tables, list):
        return []
    loaded: list[dict[str, object]] = []
    for raw_table in cast(list[object], tables):
        loaded.append(_toml_object(raw_table, label="allowlist"))
    return loaded


def _joined_paths() -> str:
    """Concatenate allowlist path patterns.

    Returns:
        Newline-joined path regexes.
    """

    chunks: list[str] = []
    for table in _allowlists():
        chunks.extend(_string_values(table.get("paths")))
    return "\n".join(chunks)


def _joined_regexes() -> str:
    """Concatenate allowlist secret-line regexes.

    Returns:
        Newline-joined line regexes.
    """

    chunks: list[str] = []
    for table in _allowlists():
        chunks.extend(_string_values(table.get("regexes")))
    return "\n".join(chunks)


def test_nightly_generic_api_key_false_positives_are_allowlisted() -> None:
    """Schedule scans the full git history; push scans only new commits.

    Nightly preflight failed on seven ``generic-api-key`` hits that are
    inert canaries, empty example names, an Action pin SHA, and image
    digests. The hosted-ingest example allowlist cannot use ``$`` after
    ``OPENAI_API_KEY=`` because Gitleaks treats that assignment plus the
    following ``LANGSMITH_TRACING=true`` line as one match. Those
    patterns must stay allowlisted so schedule and push both stay green.
    """

    paths = _joined_paths()
    regexes = _joined_regexes()
    assert "tests/.+" in paths
    assert r"scripts/check\.py" in paths
    assert r"\.env\.hosted-ingest\.example" in paths
    assert "phase10_constants" in paths
    assert "docs/deployment/phase-09/" in paths
    assert "sk-canarysecretFORBID" in regexes
    assert "OPENAI_API_KEY=" in regexes
    assert "CONFIGURE_AWS_CREDENTIALS_SHA" in regexes
    assert "sha256:[0-9a-f]{64}" in regexes
    assert "zdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24i" in regexes
