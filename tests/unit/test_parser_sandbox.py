"""Unit tests for parser sandbox launcher configuration."""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Sequence
from typing import cast

import pytest
from smart_rag_core.ingestion.parser.archive import reject_archive_bomb
from smart_rag_core.ingestion.parser.exceptions import (
    ParserLimitExceeded,
    ParserSandboxError,
)
from smart_rag_core.ingestion.parser.limits import PARSER_SANDBOX_MAX_INPUT_BYTES
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
)
from smart_rag_core.ingestion.parser.service import ParserService
from smart_rag_core.ingestion.parser.types import ParseDisposition

from tests.fixtures.parser import build_archive_bomb
from tests.unit.typed_attrs import typed_attr


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


def test_default_launcher_requires_docker_when_cli_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default launcher must not silently parse in-process when Docker is absent."""

    def _missing_docker(_name: str) -> None:
        """Pretend Docker is absent.

        Args:
            _name: Executable name.

        Returns:
            Always ``None``.
        """

        return None

    monkeypatch.setattr(
        "smart_rag_core.ingestion.parser.sandbox.launcher.shutil.which",
        _missing_docker,
    )
    launcher = ParserSandboxLauncher()
    assert launcher.config.use_docker is True
    payload = b"hello parser\n"
    digest = hashlib.sha256(payload).hexdigest()
    with pytest.raises(ParserSandboxError, match="docker executable not found"):
        launcher.run(
            payload=payload,
            content_hash=digest,
            filename="sample.txt",
            format_key="text",
        )


def test_parser_service_inprocess_only_when_test_env_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ParserService uses Docker unless ALLOW_INPROCESS_PARSER and APP_ENV=test."""

    monkeypatch.delenv("ALLOW_INPROCESS_PARSER", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    docker_service = ParserService()
    assert typed_attr(docker_service, "_launcher").config.use_docker is True

    monkeypatch.setenv("ALLOW_INPROCESS_PARSER", "true")
    monkeypatch.setenv("APP_ENV", "test")
    test_service = ParserService()
    assert typed_attr(test_service, "_launcher").config.use_docker is False


def test_archive_parent_path_is_rejected() -> None:
    """ZIP members that traverse parent directories fail closed."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.txt", "stolen")
    with pytest.raises(ParserLimitExceeded, match="parent-traversing"):
        reject_archive_bomb(buffer.getvalue())


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

    commands: list[tuple[str, ...]] = []

    def _run(cmd: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        """Timeout on ``docker run``; succeed on ``docker kill`` / ``rm``.

        Args:
            cmd: Subprocess argument list.
            **_kwargs: Unused subprocess.run keyword arguments.

        Returns:
            A successful completed process for kill/rm.

        Raises:
            TimeoutExpired: Simulated hung ``docker run``.
            TypeError: When ``cmd`` is not a string sequence.
        """

        if not isinstance(cmd, (list, tuple)):
            raise TypeError("expected docker argv")
        argv = tuple(str(part) for part in cast(Sequence[object], cmd))
        commands.append(argv)
        if len(argv) > 1 and argv[1] == "run":
            raise subprocess.TimeoutExpired(cmd="docker", timeout=1)
        return subprocess.CompletedProcess(
            args=list(argv),
            returncode=0,
            stdout="",
            stderr="",
        )

    def _which(_name: str) -> str:
        """Return a fake Docker path so the launcher attempts a container run.

        Args:
            _name: Executable name passed to ``shutil.which``.

        Returns:
            Absolute path treated as a present Docker binary.
        """

        return "/usr/bin/docker"

    monkeypatch.setattr(subprocess, "run", _run)
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
    assert any(len(cmd) > 1 and cmd[1] == "kill" for cmd in commands)


def test_docker_run_decodes_sandbox_stdio_as_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows cp1252 must not decode parser-sandbox stdout.

    Args:
        monkeypatch: Used to stub Docker CLI presence and ``subprocess.run``.
    """

    import subprocess

    captured: dict[str, object] = {}

    def _run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Capture decode kwargs and return a failed docker run.

        Args:
            cmd: Subprocess argument list.
            **kwargs: Forwarded ``subprocess.run`` keyword arguments.

        Returns:
            A failed completed process so the launcher does not read files.

        Raises:
            TypeError: When ``cmd`` is not a string sequence.
        """

        if not isinstance(cmd, (list, tuple)):
            raise TypeError("expected docker argv")
        argv = tuple(str(part) for part in cast(Sequence[object], cmd))
        if len(argv) > 1 and argv[1] == "run":
            captured.update(kwargs)
        return subprocess.CompletedProcess(
            args=list(argv),
            returncode=1,
            stdout="",
            stderr="sandbox failed",
        )

    monkeypatch.setattr(subprocess, "run", _run)

    def _docker_which(_name: str) -> str:
        """Return a fake Docker path.

        Args:
            _name: Executable name.

        Returns:
            Fake absolute Docker path.
        """

        return "/usr/bin/docker"

    monkeypatch.setattr(
        "smart_rag_core.ingestion.parser.sandbox.launcher.shutil.which",
        _docker_which,
    )
    launcher = ParserSandboxLauncher(
        config=SandboxLaunchConfig(
            image="smart-rag-parser-sandbox:local",
            use_docker=True,
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
    assert captured.get("encoding") == "utf-8"
    assert captured.get("errors") == "replace"


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


def test_unrelated_pid_does_not_match_host_worker_identity() -> None:
    """Stop/verify must not kill a reused PID that is not this launcher."""

    from scripts.ops.run_laptop_ingest_worker import (
        LAUNCHER_PATH,
        WorkerProcessIdentity,
        identities_match,
    )

    recorded = WorkerProcessIdentity(
        pid=4242,
        start_time="2026-09-16T12:00:00.0000000Z",
        command_line=f"uv run python {LAUNCHER_PATH}",
    )
    reused = WorkerProcessIdentity(
        pid=4242,
        start_time="2026-09-16T12:05:00.0000000Z",
        command_line="uv run python other_tool.py",
    )
    assert identities_match(recorded, recorded) is True
    assert identities_match(recorded, reused) is False
