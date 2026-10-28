#!/usr/bin/env python3
"""Run hard-failing Smart RAG quality tiers from one cross-platform CLI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from smart_rag_core.settings.base import get_process_environ, snapshot_process_environ

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

# Published Supabase local demo anon JWT. Same value as Playwright. Not a secret.
_LOCAL_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)
_FRONTEND_PUBLIC_BUILD_ENV: tuple[tuple[str, str], ...] = (
    ("NEXT_PUBLIC_API_BASE_URL", "http://127.0.0.1:8000"),
    ("NEXT_PUBLIC_SUPABASE_URL", "https://placeholder.supabase.co"),
    ("NEXT_PUBLIC_SUPABASE_ANON_KEY", _LOCAL_SUPABASE_ANON_KEY),
)


@dataclass(frozen=True)
class Command:
    """One child quality command.

    Attributes:
        label: User-facing check description.
        arguments: Exact shell-free child argument vector.
        extra_environ: Public placeholders merged with ``setdefault`` into the
            child environment. Existing process values win.
    """

    label: str
    arguments: tuple[str, ...]
    extra_environ: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CheckOptions:
    """Validated quality-runner options.

    Attributes:
        tier: Required quality tier.
        mermaid_puppeteer_config: Optional explicit Puppeteer config forwarded
            only to the maintained-documentation renderer.
    """

    tier: Tier
    mermaid_puppeteer_config: Path | None


def _pytest_args(path: str) -> tuple[str, ...]:
    """Build pytest path arguments with optional CI traceback flags.

    Args:
        path: Test directory relative to the repository root
            (``tests/unit`` or ``tests/contract``).

    Returns:
        A tuple that starts with ``path``. When the ``CI`` environment
        variable is truthy, ``--tb=short`` and ``-ra`` follow the path so
        GitHub Actions logs stay compact. Local runs keep pytest defaults
        when ``CI`` is unset or empty.
    """

    if get_process_environ("CI"):
        return (path, "--tb=short", "-ra")
    return (path,)


class CheckRunner:
    """Execute repository checks and preserve the first child failure code."""

    def __init__(
        self,
        repo_root: Path,
        *,
        mermaid_puppeteer_config: Path | None = None,
    ) -> None:
        """Initialize a runner rooted at the repository.

        Args:
            repo_root: Directory from which every child command runs.
            mermaid_puppeteer_config: Optional Puppeteer config forwarded to
                Mermaid rendering. Local runs retain the sandbox by default.
        """

        self._repo_root = repo_root
        self._python = sys.executable
        self._pnpm = shutil.which("pnpm") or "pnpm"
        self._mermaid_puppeteer_config = mermaid_puppeteer_config

    def _playwright_install_chromium(self) -> tuple[str, ...]:
        """Install only Chromium for the frontend Playwright suite.

        Linux CI uses ``--with-deps``. Windows hosts skip that flag because
        Playwright documents it for Debian/Ubuntu package dependencies.

        Returns:
            Exact argument vector for ``playwright install chromium``.
        """

        arguments = [
            self._pnpm,
            "--filter",
            "smart-rag-frontend",
            "exec",
            "playwright",
            "install",
        ]
        if os.name != "nt":
            arguments.append("--with-deps")
        arguments.append("chromium")
        return tuple(arguments)

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

        for command in self.commands_for_tier(tier):
            print(f"[{tier}] {command.label}", flush=True)
            print(f"$ {' '.join(command.arguments)}", flush=True)
            try:
                child_env = None
                if command.extra_environ:
                    child_env = snapshot_process_environ()
                    for key, value in command.extra_environ:
                        child_env.setdefault(key, value)
                completed = subprocess.run(  # noqa: S603 - fixed repository commands
                    command.arguments,
                    cwd=self._repo_root,
                    check=False,
                    env=child_env,
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

    def commands_for_tier(self, tier: Tier) -> tuple[Command, ...]:
        """Build exact child commands for a non-composite tier.

        Args:
            tier: Tier other than ``fast``.

        Returns:
            Ordered commands for the tier. Unit and contract pytest
            argument tuples append ``--tb=short`` and ``-ra`` after the
            test path when ``CI`` is truthy; local runs omit those flags.

        Raises:
            ValueError: If ``tier`` is unknown or composite.
        """

        python_module = (self._python, "-m")
        docs_arguments = (self._python, "scripts/check_docs.py")
        if self._mermaid_puppeteer_config is not None:
            docs_arguments += (
                "--puppeteer-config",
                str(self._mermaid_puppeteer_config),
            )
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
            "types": (
                Command(
                    "Pyright error-count ratchet",
                    (self._python, "scripts/ci/check_pyright_baseline.py"),
                ),
                Command("Pyright strict typing", (*python_module, "pyright")),
            ),
            "unit": (
                Command(
                    "Python unit tests",
                    (*python_module, "pytest", *_pytest_args("tests/unit")),
                ),
                Command(
                    "Phase 6 eval registry",
                    (self._python, "scripts/ci/check_phase6_eval_registry.py"),
                ),
            ),
            "contract": (
                Command(
                    "Python contract tests",
                    (*python_module, "pytest", *_pytest_args("tests/contract")),
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
                    docs_arguments,
                ),
                Command(
                    "Frontend action inventory",
                    (self._python, "scripts/check_frontend_action_inventory.py"),
                ),
            ),
            "frontend": (
                Command(
                    "Frontend ESLint",
                    (self._pnpm, "--filter", "smart-rag-frontend", "lint"),
                ),
                Command(
                    "Frontend route type generation",
                    (
                        self._pnpm,
                        "--filter",
                        "smart-rag-frontend",
                        "exec",
                        "next",
                        "typegen",
                    ),
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
                    extra_environ=_FRONTEND_PUBLIC_BUILD_ENV,
                ),
                Command(
                    "Playwright Chromium install",
                    self._playwright_install_chromium(),
                ),
                Command(
                    "Playwright Chromium e2e",
                    (
                        self._pnpm,
                        "--filter",
                        "smart-rag-frontend",
                        "exec",
                        "playwright",
                        "test",
                    ),
                    extra_environ=_FRONTEND_PUBLIC_BUILD_ENV,
                ),
                Command(
                    "Playwright Web quality fixtures",
                    (
                        self._pnpm,
                        "--filter",
                        "smart-rag-frontend",
                        "exec",
                        "playwright",
                        "test",
                        "--config",
                        "playwright.web-fixture.config.ts",
                    ),
                ),
            ),
            "fast": (),
        }
        if tier == "fast":
            raise ValueError("fast is a composite tier")
        return commands[tier]


def parse_options(argv: Sequence[str] | None = None) -> CheckOptions:
    """Parse the required tier and optional Mermaid renderer configuration.

    Args:
        argv: Optional argument sequence, excluding the program name.

    Returns:
        Validated quality-runner options.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tier",
        required=True,
        choices=TIERS,
        help="Quality tier to execute.",
    )
    parser.add_argument(
        "--mermaid-puppeteer-config",
        help="Explicit Puppeteer JSON config forwarded to Mermaid CLI.",
    )
    parsed = parser.parse_args(argv)
    raw_config = cast(str | None, parsed.mermaid_puppeteer_config)
    return CheckOptions(
        tier=cast(Tier, parsed.tier),
        mermaid_puppeteer_config=Path(raw_config).resolve() if raw_config else None,
    )


def parse_tier(argv: Sequence[str] | None = None) -> Tier:
    """Parse and return only the required quality tier.

    Args:
        argv: Optional argument sequence, excluding the program name.

    Returns:
        Validated tier name.
    """

    return parse_options(argv).tier


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected quality tier.

    Args:
        argv: Optional argument sequence, excluding the program name.

    Returns:
        Selected tier exit code.
    """

    repo_root = Path(__file__).resolve().parents[1]
    options = parse_options(argv)
    return CheckRunner(
        repo_root,
        mermaid_puppeteer_config=options.mermaid_puppeteer_config,
    ).run_tier(options.tier)


if __name__ == "__main__":
    raise SystemExit(main())
