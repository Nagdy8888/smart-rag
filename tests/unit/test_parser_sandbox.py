"""Unit tests for parser sandbox launcher configuration."""

from __future__ import annotations

import hashlib

from smart_rag_core.ingestion.parser.limits import PARSER_SANDBOX_MAX_INPUT_BYTES
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
)
from smart_rag_core.ingestion.parser.types import ParseDisposition


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
