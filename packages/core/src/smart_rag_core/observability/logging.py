"""Structured JSON logging with correlation context and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_RUN_ID: ContextVar[str | None] = ContextVar("run_id", default=None)
_JOB_ID: ContextVar[str | None] = ContextVar("job_id", default=None)

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[REDACTED]"),
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
        "Bearer [REDACTED]",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|password|passwd|token|secret)"
            r"(\s*[:=]\s*)([^\s,;]+)"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<user>[^:/@\s]+):[^@\s]+@"),
        r"\g<scheme>\g<user>:[REDACTED]@",
    ),
)


def redact_text(value: str, *, max_length: int = 2_048) -> str:
    """Redact common credential forms and bound logged text.

    Args:
        value: Text that may contain credentials.
        max_length: Maximum retained character count.

    Returns:
        Redacted text, truncated with a marker when necessary.
    """

    redacted = value.replace("\r", "\\r").replace("\n", "\\n")
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    if len(redacted) > max_length:
        return f"{redacted[:max_length]}...[TRUNCATED]"
    return redacted


class JsonLogFormatter(logging.Formatter):
    """Render one sanitized JSON object per log record."""

    def __init__(self, *, service: str, environment: str) -> None:
        """Initialize stable deployment metadata.

        Args:
            service: Deployable service name.
            environment: Deployment environment name.
        """

        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record without raw exception or secret values.

        Args:
            record: Standard-library log record.

        Returns:
            A compact JSON object containing required metadata and available
            correlation identifiers.
        """

        raw_event = record.__dict__.get("event", record.msg)
        event = redact_text(str(raw_event), max_length=256)
        payload: dict[str, str] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "environment": self._environment,
            "event": event,
            "message": redact_text(record.getMessage()),
        }
        for field, value in (
            ("request_id", _REQUEST_ID.get()),
            ("run_id", _RUN_ID.get()),
            ("job_id", _JOB_ID.get()),
        ):
            if value is not None:
                payload[field] = redact_text(value, max_length=128)
        if record.exc_info is not None and record.exc_info[1] is not None:
            payload["exception_type"] = type(record.exc_info[1]).__name__
            payload["exception_message"] = "[REDACTED]"
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_json_logging(
    *,
    service: str,
    environment: str,
    level: str = "INFO",
) -> None:
    """Configure root logging to emit sanitized JSON to standard output.

    Args:
        service: Deployable service name included in every record.
        environment: Deployment environment name included in every record.
        level: Standard Python logging level name.

    Raises:
        ValueError: If ``level`` is not a known logging level.

    Side Effects:
        Replaces root logger handlers with one stdout handler.
    """

    resolved_level = logging.getLevelNamesMapping().get(level.upper())
    if resolved_level is None:
        raise ValueError(f"Unknown log level: {redact_text(level, max_length=32)}")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(service=service, environment=environment))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)


@contextmanager
def correlation_context(
    *,
    request_id: str | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
) -> Generator[None]:
    """Bind correlation identifiers for logs emitted in the current context.

    Args:
        request_id: HTTP request correlation identifier.
        run_id: Query or graph run identifier.
        job_id: Background job identifier.

    Yields:
        Control while correlation values are bound.

    Side Effects:
        Sets and then restores context-local correlation variables.
    """

    tokens: tuple[tuple[ContextVar[str | None], Token[str | None]], ...] = (
        (_REQUEST_ID, _REQUEST_ID.set(request_id)),
        (_RUN_ID, _RUN_ID.set(run_id)),
        (_JOB_ID, _JOB_ID.set(job_id)),
    )
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
