"""Unit tests for correlated JSON logging and credential redaction."""

from __future__ import annotations

import json
import logging
from io import StringIO
from typing import cast

from smart_rag_core.observability import JsonLogFormatter, correlation_context


def test_json_logs_include_required_metadata_and_redact_secrets() -> None:
    """Structured records retain correlations while removing credential forms."""

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter(service="backend", environment="test"))
    logger = logging.getLogger("tests.structured-redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with correlation_context(request_id="req-123", run_id="run-456", job_id="job-789"):
        logger.info(
            (
                "api_key=sk-abcdefghijklmnopqrstuvwxyz "
                "password=hunter2 "
                "Authorization: Bearer eyJ.private.token "
                "postgresql://reader:db-password@example.test/db"
            ),
            extra={"event": "security.redaction.probe"},
        )

    payload = cast(dict[str, str], json.loads(stream.getvalue()))
    serialized = json.dumps(payload)
    assert payload["timestamp"]
    assert payload["level"] == "INFO"
    assert payload["service"] == "backend"
    assert payload["environment"] == "test"
    assert payload["event"] == "security.redaction.probe"
    assert payload["request_id"] == "req-123"
    assert payload["run_id"] == "run-456"
    assert payload["job_id"] == "job-789"
    assert "hunter2" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "eyJ.private.token" not in serialized
    assert "db-password" not in serialized


def test_exception_logs_omit_exception_message_and_private_source() -> None:
    """Exception metadata exposes only type plus a fixed redacted message."""

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter(service="worker", environment="test"))
    logger = logging.getLogger("tests.exception-redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)

    try:
        raise RuntimeError("private source paragraph and token=top-secret")
    except RuntimeError:
        logger.exception(
            "bounded failure",
            extra={"event": "worker.failure"},
        )

    payload = cast(dict[str, str], json.loads(stream.getvalue()))
    serialized = json.dumps(payload)
    assert payload["exception_type"] == "RuntimeError"
    assert payload["exception_message"] == "[REDACTED]"
    assert "private source paragraph" not in serialized
    assert "top-secret" not in serialized
