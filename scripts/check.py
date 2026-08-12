#!/usr/bin/env python3
"""Run hard-failing Smart RAG quality tiers from one cross-platform CLI."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

Tier = Literal[
    "format",
    "lint",
    "types",
    "unit",
    "contract",
    "docs",
    "frontend",
    "fast",
]
TIERS: tuple[Tier, ...] = (
    "format",
    "lint",
    "types",
    "unit",
    "contract",
    "docs",
    "frontend",
    "fast",
)
FAST_TIERS: tuple[Tier, ...] = (
    "format",
    "lint",
    "types",
    "unit",
    "contract",
    "docs",
    "frontend",
)


@dataclass(frozen=True)
class Command:
    """One child quality command.

    Attributes:
        label: User-facing check description.
        arguments: Exact shell-free child argument vector.
    """

    label: str
    arguments: tuple[str, ...]


class CheckRunner:
    """Execute repository checks and preserve the first child failure code."""

    def __init__(self, repo_root: Path) -> None:
        """Initialize a runner rooted at the repository.

        Args:
            repo_root: Directory from which every child command runs.
        """

        self._repo_root = repo_root
        self._python = sys.executable
        self._pnpm = shutil.which("pnpm") or "pnpm"

    def run_tier(self, tier: Tier) -> int:
        """Run one tier, stopping at its first required failure.

        Args:
            tier: Named quality tier.

        Returns:
            Zero on success; otherwise the exact first failing child exit code.
            Missing executables return the conventional code 127.
        """

        if tier == "fast":
            for child_tier in FAST_TIERS:
                result = self.run_tier(child_tier)
                if result != 0:
                    return result
            return 0

        for command in self._commands_for_tier(tier):
            print(f"[{tier}] {command.label}", flush=True)
            print(f"$ {' '.join(command.arguments)}", flush=True)
            try:
                completed = subprocess.run(  # noqa: S603 - fixed repository commands
                    command.arguments,
                    cwd=self._repo_root,
                    check=False,
                )
            except FileNotFoundError:
                print(
                    f"ERROR: required executable not found: {command.arguments[0]}",
                    file=sys.stderr,
                    flush=True,
                )
                return 127
            if completed.returncode != 0:
                return completed.returncode
        return 0

    def _commands_for_tier(self, tier: Tier) -> tuple[Command, ...]:
        """Build exact child commands for a non-composite tier.

        Args:
            tier: Tier other than ``fast``.

        Returns:
            Ordered commands for the tier.

        Raises:
            ValueError: If ``tier`` is unknown or composite.
        """

        python_module = (self._python, "-m")
        commands: dict[Tier, tuple[Command, ...]] = {
            "format": (
                Command(
                    "Ruff formatting",
                    (*python_module, "ruff", "format", "--check", "."),
                ),
            ),
            "lint": (
                Command(
                    "Ruff lint and pydocstyle",
                    (*python_module, "ruff", "check", "."),
                ),
            ),
            "types": (Command("Pyright strict typing", (*python_module, "pyright")),),
            "unit": (
                Command(
                    "Python unit tests",
                    (*python_module, "pytest", "tests/unit"),
                ),
            ),
            "contract": (
                Command(
                    "Python contract tests",
                    (*python_module, "pytest", "tests/contract"),
                ),
            ),
            "docs": (
                Command(
                    "Markdown lint",
                    (
                        self._pnpm,
                        "exec",
                        "markdownlint-cli2",
                        "docs/**/*.md",
                    ),
                ),
                Command(
                    "Markdown links and Mermaid rendering",
                    (self._python, "scripts/check_docs.py"),
                ),
            ),
            "frontend": (
                Command(
                    "Frontend ESLint",
                    (self._pnpm, "--filter", "smart-rag-frontend", "lint"),
                ),
                Command(
                    "Frontend TypeScript strict",
                    (
                        self._pnpm,
                        "--filter",
                        "smart-rag-frontend",
                        "exec",
                        "tsc",
                        "--noEmit",
                    ),
                ),
                Command(
                    "Frontend Vitest",
                    (self._pnpm, "--filter", "smart-rag-frontend", "test"),
                ),
                Command(
                    "Frontend production build",
                    (self._pnpm, "--filter", "smart-rag-frontend", "build"),
                ),
                Command(
                    "Playwright installation contract",
                    (
                        self._pnpm,
                        "--filter",
                        "smart-rag-frontend",
                        "exec",
                        "playwright",
                        "--version",
                    ),
                ),
            ),
            "fast": (),
        }
        if tier == "fast":
            raise ValueError("fast is a composite tier")
        return commands[tier]


def parse_tier(argv: Sequence[str] | None = None) -> Tier:
    """Parse the required tier from command-line arguments.

    Args:
        argv: Optional argument sequence, excluding the program name.

    Returns:
        Validated tier name.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tier",
        required=True,
        choices=TIERS,
        help="Quality tier to execute.",
    )
    parsed = parser.parse_args(argv)
    return cast(Tier, parsed.tier)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected quality tier.

    Args:
        argv: Optional argument sequence, excluding the program name.

    Returns:
        Selected tier exit code.
    """

    repo_root = Path(__file__).resolve().parents[1]
    return CheckRunner(repo_root).run_tier(parse_tier(argv))


if __name__ == "__main__":
    raise SystemExit(main())
