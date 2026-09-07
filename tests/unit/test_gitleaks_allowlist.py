"""Gitleaks allowlists must cover Nightly full-history false positives."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GITLEAKS_TOML = REPO_ROOT / ".gitleaks.toml"


def _allowlists() -> list[dict[str, object]]:
    """Load ``[[allowlists]]`` tables from the committed Gitleaks config.

    Returns:
        Allowlist objects from ``.gitleaks.toml``.
    """

    parsed = tomllib.loads(GITLEAKS_TOML.read_text(encoding="utf-8"))
    tables = parsed.get("allowlists")
    assert isinstance(tables, list)
    return [item for item in tables if isinstance(item, dict)]


def _joined_paths() -> str:
    """Concatenate allowlist path patterns.

    Returns:
        Newline-joined path regexes.
    """

    chunks: list[str] = []
    for table in _allowlists():
        paths = table.get("paths")
        if isinstance(paths, list):
            chunks.extend(str(item) for item in paths)
    return "\n".join(chunks)


def _joined_regexes() -> str:
    """Concatenate allowlist secret-line regexes.

    Returns:
        Newline-joined line regexes.
    """

    chunks: list[str] = []
    for table in _allowlists():
        regexes = table.get("regexes")
        if isinstance(regexes, list):
            chunks.extend(str(item) for item in regexes)
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
