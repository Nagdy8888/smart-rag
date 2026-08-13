"""Unit tests for the canonical hard-failing quality command runner."""

from __future__ import annotations

from pathlib import Path

from scripts.check import CheckRunner, parse_options
from scripts.check_docs import parse_options as parse_docs_options


def test_unit_tier_preserves_pytest_zero_collection_exit_code(
    tmp_path: Path,
) -> None:
    """An empty unit selection must return pytest's exit code 5."""

    (tmp_path / "tests" / "unit").mkdir(parents=True)

    result = CheckRunner(tmp_path).run_tier("unit")

    assert result == 5


def test_mermaid_puppeteer_config_is_explicitly_parsed(tmp_path: Path) -> None:
    """CI browser sandbox workarounds require an explicit repository path."""

    config = tmp_path / "puppeteer.json"
    config.write_text('{"args": ["--no-sandbox"]}', encoding="utf-8")

    runner_options = parse_options(
        [
            "--tier",
            "fast",
            "--mermaid-puppeteer-config",
            str(config),
        ]
    )
    docs_options = parse_docs_options(["--puppeteer-config", str(config)])

    assert runner_options.mermaid_puppeteer_config == config.resolve()
    assert docs_options.puppeteer_config == config.resolve()
