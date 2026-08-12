"""Unit tests for the canonical hard-failing quality command runner."""

from __future__ import annotations

from pathlib import Path

from scripts.check import CheckRunner


def test_unit_tier_preserves_pytest_zero_collection_exit_code(
    tmp_path: Path,
) -> None:
    """An empty unit selection must return pytest's exit code 5."""

    (tmp_path / "tests" / "unit").mkdir(parents=True)

    result = CheckRunner(tmp_path).run_tier("unit")

    assert result == 5
