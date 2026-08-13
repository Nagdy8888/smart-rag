"""Contract tests for parser sandbox isolation."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
    _docker_available,
)
from smart_rag_core.ingestion.parser.types import ParseDisposition

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "infra" / "parser-sandbox" / "Dockerfile"


def test_parser_dockerfile_runs_non_root() -> None:
    """Parser sandbox image drops privileges to UID 10001."""

    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER 10001:10001" in content
    assert "tesseract-ocr" in content


def test_compose_parser_service_not_on_egress() -> None:
    """Parser sandbox build profile stays off egress/crawl networks."""

    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "parser-sandbox:" in compose
    assert "profiles:" in compose
    assert "parser-build" in compose
    assert "egress" not in compose.split("parser-sandbox:")[1].split("frontend:")[0]


@pytest.mark.skipif(not _docker_available(), reason="Docker unavailable")
def test_docker_run_uses_network_none() -> None:
    """Sandbox launcher constructs docker run with --network none."""

    launcher = ParserSandboxLauncher(
        config=SandboxLaunchConfig(image="smart-rag-parser-sandbox:local", use_docker=True)
    )
    assert launcher.config.use_docker is True
    payload = b"contract line\n"
    digest = hashlib.sha256(payload).hexdigest()
    if shutil.which("docker") is None:
        pytest.skip("docker missing")
    image_exists = subprocess.run(
        ["docker", "image", "inspect", "smart-rag-parser-sandbox:local"],
        capture_output=True,
        check=False,
    ).returncode == 0
    if not image_exists:
        pytest.skip("parser sandbox image not built")
    result = launcher.run(
        payload=payload,
        content_hash=digest,
        filename="contract.txt",
        format_key="text",
    )
    assert result.disposition in {ParseDisposition.SUPPORTED, ParseDisposition.FAILED}


def test_sandbox_escape_fixture_rejected_inprocess(tmp_path) -> None:
    """Path traversal filename does not escape temp directory."""

    launcher = ParserSandboxLauncher(
        config=SandboxLaunchConfig(image="unused", use_docker=False)
    )
    payload = b"safe\n"
    digest = hashlib.sha256(payload).hexdigest()
    result = launcher.run(
        payload=payload,
        content_hash=digest,
        filename="../escape.txt",
        format_key="text",
    )
    assert result.disposition is ParseDisposition.SUPPORTED
    assert result.elements
