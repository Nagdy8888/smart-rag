"""Unit tests for parser sandbox launcher configuration."""

from __future__ import annotations

import hashlib

import pytest
from smart_rag_core.ingestion.parser.limits import PARSER_SANDBOX_MAX_INPUT_BYTES
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
)
from smart_rag_core.ingestion.parser.types import ParseDisposition

from tests.fixtures.parser import build_archive_bomb


def test_oversize_input_fails_without_partial_elements() -> None:
    """Input exceeding byte cap returns failed disposition with zero elements."""

    launcher = ParserSandboxLauncher()
    payload = b"x" * (PARSER_SANDBOX_MAX_INPUT_BYTES + 1)
    digest = hashlib.sha256(payload).hexdigest()
    result = launcher.run(
        payload=payload,
        content_hash=digest,
        filename="big.txt",
        format_key="text",
    )
    assert result.disposition is ParseDisposition.FAILED
    assert result.coverage.total_elements == 0


def test_inprocess_parse_text_fixture() -> None:
    """In-process sandbox path parses plain text when Docker is disabled."""

    launcher = ParserSandboxLauncher(
        config=SandboxLaunchConfig(image="unused", use_docker=False)
    )
    payload = b"hello parser\n"
    digest = hashlib.sha256(payload).hexdigest()
    result = launcher.run(
        payload=payload,
        content_hash=digest,
        filename="sample.txt",
        format_key="text",
    )
    assert result.disposition is ParseDisposition.SUPPORTED
    assert result.elements


def test_archive_bomb_hits_expansion_limit() -> None:
    """ZIP bombs fail on expansion ratio, not the raw input-byte cap."""

    launcher = ParserSandboxLauncher(
        config=SandboxLaunchConfig(image="unused", use_docker=False)
    )
    payload, digest = build_archive_bomb()
    assert len(payload) < PARSER_SANDBOX_MAX_INPUT_BYTES
    result = launcher.run(
        payload=payload,
        content_hash=digest,
        filename="bomb.zip",
        format_key="zip",
    )
    assert result.disposition is ParseDisposition.FAILED
    assert result.coverage.total_elements == 0
    assert "archive_expansion_ratio" in (result.detail or "")


def test_parser_sandbox_kill_timeout_returns_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker sandbox kill-timeout yields failed disposition with zero elements."""

    import subprocess

    def _timeout(*_args: object, **_kwargs: object) -> object:
        """Raise TimeoutExpired to simulate a hung Docker sandbox.

        Args:
            *_args: Unused subprocess.run positional arguments.
            **_kwargs: Unused subprocess.run keyword arguments.

        Returns:
            Never returns; always raises.

        Raises:
            TimeoutExpired: Simulated Docker kill-timeout.
        """

        raise subprocess.TimeoutExpired(cmd="docker", timeout=1)

    def _which(_name: str) -> str:
        """Return a fake Docker path so the launcher attempts a container run.

        Args:
            _name: Executable name passed to ``shutil.which``.

        Returns:
            Absolute path treated as a present Docker binary.
        """

        return "/usr/bin/docker"

    monkeypatch.setattr(subprocess, "run", _timeout)
    monkeypatch.setattr(
        "smart_rag_core.ingestion.parser.sandbox.launcher.shutil.which",
        _which,
    )
    launcher = ParserSandboxLauncher(
        config=SandboxLaunchConfig(
            image="smart-rag-parser-sandbox:local",
            use_docker=True,
            timeout_seconds=1,
        )
    )
    payload = b"hello parser\n"
    digest = hashlib.sha256(payload).hexdigest()
    result = launcher.run(
        payload=payload,
        content_hash=digest,
        filename="sample.txt",
        format_key="text",
    )
    assert result.disposition is ParseDisposition.FAILED
    assert result.coverage.total_elements == 0
    assert "timeout" in (result.detail or "")


def test_parser_package_init_is_sandbox_importable() -> None:
    """Parser package init must not import governance or JWKS into the sandbox."""

    import ast
    from pathlib import Path

    init_path = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "core"
        / "src"
        / "smart_rag_core"
        / "ingestion"
        / "parser"
        / "__init__.py"
    )
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert not any("service" in name for name in imported)
    assert not any("governance" in name for name in imported)
    assert not any("jwks" in name for name in imported)
