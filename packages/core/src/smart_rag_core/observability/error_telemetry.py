"""GlitchTip error groups and Grafana OTLP logs/traces.

Both exporters stay off unless their settings flags are true. Payloads reuse
the JSON log redaction rules: correlation ids, event names, and exception
types are exported; secrets, request bodies, and passage text are not.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

import sentry_sdk
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.types import Breadcrumb, Event, Hint

from smart_rag_core.observability.logging import current_correlation_ids, redact_text
from smart_rag_core.settings.base import SharedSettings, parse_otlp_headers

_glitchtip_ready = False
_otel_ready = False
_logger_provider: LoggerProvider | None = None
_tracer_provider: TracerProvider | None = None

_FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "cookies",
        "email",
        "html",
        "page_content",
        "passage",
        "password",
        "prompt",
        "query",
        "retrieved_text",
        "secret",
        "snippet",
        "source",
        "token",
    }
)
_FRAME_PRIVATE_KEYS = ("vars", "pre_context", "post_context", "context_line")
_REQUEST_PRIVATE_KEYS = ("cookies", "headers", "data", "env", "query_string")
_SCRUB_DEPTH = 6


def scrub_glitchtip_event(event: Event, hint: Hint) -> Event:
    """Remove private fields and redact messages before a GlitchTip send.

    Args:
        event: Sentry event payload about to be exported.
        hint: SDK hint. Unused; accepted so this function can be ``before_send``.

    Returns:
        The same event, with request bodies, frame variables, source context,
        and forbidden keys removed. Exception text is passed through
        ``redact_text``. Correlation ids are added as tags.

    Side Effects:
        Mutates ``event`` in place.
    """

    del hint
    payload = cast(dict[str, Any], event)
    request = _as_dict(payload.get("request"))
    if request is not None:
        for key in _REQUEST_PRIVATE_KEYS:
            request.pop(key, None)
    payload.pop("user", None)
    _redact_exception_values(payload)
    logentry = _as_dict(payload.get("logentry"))
    if logentry is not None:
        message = logentry.get("message")
        if isinstance(message, str):
            logentry["message"] = redact_text(message)
        logentry.pop("params", None)
    message = payload.get("message")
    if isinstance(message, str):
        payload["message"] = redact_text(message)
    _strip_forbidden_keys(payload.get("extra"))
    _strip_forbidden_keys(payload.get("contexts"))
    tags = _as_dict(payload.get("tags"))
    if tags is None:
        tags = {}
        payload["tags"] = tags
    for key, value in current_correlation_ids().items():
        tags[key] = value
    return event


def scrub_glitchtip_breadcrumb(crumb: Breadcrumb, hint: Hint) -> Breadcrumb:
    """Redact one GlitchTip breadcrumb message and drop its data bag.

    Args:
        crumb: Breadcrumb about to be stored.
        hint: SDK hint. Unused.

    Returns:
        The same breadcrumb with a redacted message and no ``data``.
    """

    del hint
    message = crumb.get("message")
    if isinstance(message, str):
        crumb["message"] = redact_text(message)
    crumb.pop("data", None)
    return crumb


class RedactedOtelLogHandler(LoggingHandler):
    """Export the JSON log fields only, never exception text or source paths."""

    def __init__(self, logger_provider: LoggerProvider) -> None:
        """Attach to one logger provider.

        Args:
            logger_provider: Provider already wired to the OTLP log exporter.

        Side Effects:
            Sets the OTLP logger provider without calling the deprecated
            ``LoggingHandler`` constructor.
        """

        logging.Handler.__init__(self, logging.NOTSET)
        self._logger_provider = logger_provider

    def emit(self, record: logging.LogRecord) -> None:
        """Send a copy that keeps event, error type, and correlation ids.

        Args:
            record: Original log record. It is not mutated.

        Side Effects:
            Enqueues one OTLP log on the configured provider.
        """

        safe = logging.LogRecord(
            name=record.name,
            level=record.levelno,
            pathname="",
            lineno=0,
            msg=redact_text(record.getMessage()),
            args=(),
            exc_info=None,
        )
        safe.funcName = ""
        event = record.__dict__.get("event")
        if isinstance(event, str) and event:
            safe.event = redact_text(event, max_length=256)
        error_type = record.__dict__.get("error_type")
        if (
            isinstance(error_type, str)
            and error_type.isidentifier()
            and len(error_type) <= 128
        ):
            safe.error_type = error_type
        if record.exc_info is not None and record.exc_info[0] is not None:
            safe.exception_type = record.exc_info[0].__name__
        for field, value in current_correlation_ids().items():
            setattr(safe, field, value)
        super().emit(safe)


def configure_error_telemetry(settings: SharedSettings) -> dict[str, str]:
    """Start GlitchTip and Grafana export when their flags are on.

    Args:
        settings: Validated deployable settings. Disabled flags do not
            construct an exporter.

    Returns:
        Non-secret flag values that were applied. DSNs and ingest tokens
        are omitted.

    Side Effects:
        When enabled, installs a Sentry client and an OTLP log handler on
        the root logger, and sets the process tracer provider. A second
        call does not add another handler. No network call is made until
        a later export.
    """

    applied = {
        "GLITCHTIP_ENABLED": "true" if settings.glitchtip_enabled else "false",
        "OTEL_EXPORT_ENABLED": "true" if settings.otel_export_enabled else "false",
    }
    if settings.glitchtip_enabled:
        _configure_glitchtip(settings)
    if settings.otel_export_enabled:
        _configure_otel(settings)
    return applied


def flush_error_telemetry(*, timeout_seconds: float = 2.0) -> None:
    """Drain queued GlitchTip events and OTLP logs/spans.

    Args:
        timeout_seconds: Maximum wait. Values at or below zero still ask
            the SDKs to flush with a zero budget.

    Side Effects:
        Blocks the caller until the queues drain or the budget expires.
        Does nothing for exporters that were never configured.
    """

    timeout_ms = max(0, int(timeout_seconds * 1000))
    sentry_sdk.flush(timeout=timeout_seconds)
    if _tracer_provider is not None:
        _tracer_provider.force_flush(timeout_millis=timeout_ms)
    if _logger_provider is not None:
        _logger_provider.force_flush(timeout_millis=timeout_ms)


def telemetry_export_ready() -> bool:
    """Return whether an OTLP tracer provider was installed.

    Returns:
        True after a successful enabled OTLP configuration.
    """

    return _otel_ready


@contextmanager
def telemetry_span(name: str) -> Generator[None]:
    """Open a root span that carries correlation ids and no request content.

    Args:
        name: Fixed span name such as ``http.request`` or ``worker.job``.

    Yields:
        Control while the span is current. Yields immediately when OTLP
        export was not configured.

    Side Effects:
        Records ``request_id``, ``run_id``, and ``job_id`` when those
        context vars are set. Does not record URLs, headers, or messages.
    """

    if not _otel_ready:
        yield
        return
    tracer = trace.get_tracer("smart_rag.telemetry")
    with tracer.start_as_current_span(name) as span:
        for key, value in current_correlation_ids().items():
            span.set_attribute(key, value)
        yield


def _configure_glitchtip(settings: SharedSettings) -> None:
    """Install the scrubbed GlitchTip client once.

    Args:
        settings: Settings with ``glitchtip_enabled`` and a DSN.

    Side Effects:
        Calls ``sentry_sdk.init``. Later calls return without re-init.
    """

    global _glitchtip_ready
    if _glitchtip_ready:
        return
    dsn_secret = settings.glitchtip_dsn
    if dsn_secret is None:
        return
    service_name = str(getattr(settings, "service_name", "smart-rag"))
    sentry_sdk.init(
        dsn=dsn_secret.get_secret_value(),
        environment=settings.app_env.value,
        server_name=service_name,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0,
        before_send=scrub_glitchtip_event,
        before_breadcrumb=scrub_glitchtip_breadcrumb,
        integrations=[
            LoggingIntegration(
                level=None,
                event_level=logging.ERROR,
                capture_sentry_logs=False,
            ),
        ],
    )
    _glitchtip_ready = True


def _configure_otel(settings: SharedSettings) -> None:
    """Install OTLP trace and log exporters once.

    Args:
        settings: Settings with the OTLP endpoint and headers.

    Side Effects:
        Sets the process tracer and logger providers and adds one root
        log handler. Does not open a connection until the first export.
    """

    global _otel_ready, _logger_provider, _tracer_provider
    if _otel_ready:
        return
    endpoint = settings.otel_exporter_otlp_endpoint
    header_secret = settings.otel_exporter_otlp_headers
    if endpoint is None or header_secret is None:
        return
    headers = parse_otlp_headers(header_secret.get_secret_value())
    base = str(endpoint).rstrip("/")
    service_name = str(getattr(settings, "service_name", "smart-rag"))
    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": settings.app_env.value,
        }
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=_signal_endpoint(base, "traces"),
                headers=headers,
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=_signal_endpoint(base, "logs"),
                headers=headers,
            )
        )
    )
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(RedactedOtelLogHandler(logger_provider))
    _tracer_provider = tracer_provider
    _logger_provider = logger_provider
    _otel_ready = True


def _signal_endpoint(base: str, signal: str) -> str:
    """Append the OTLP signal path when the base URL does not already end with it.

    Args:
        base: Grafana OTLP base URL without a trailing slash.
        signal: ``traces`` or ``logs``.

    Returns:
        Absolute signal URL.
    """

    suffix = f"/v1/{signal}"
    if base.endswith(suffix):
        return base
    return f"{base}{suffix}"


def _redact_exception_values(event: dict[str, Any]) -> None:
    """Redact exception messages and strip frame locals.

    Args:
        event: Sentry event that may contain ``exception.values``.
    """

    exception = _as_dict(event.get("exception"))
    if exception is None:
        return
    values = _as_list(exception.get("values"))
    if values is None:
        return
    for item in values:
        value = _as_dict(item)
        if value is None:
            continue
        text = value.get("value")
        if isinstance(text, str):
            value["value"] = redact_text(text)
        stacktrace = _as_dict(value.get("stacktrace"))
        if stacktrace is None:
            continue
        frames = _as_list(stacktrace.get("frames"))
        if frames is None:
            continue
        for frame_item in frames:
            frame = _as_dict(frame_item)
            if frame is None:
                continue
            for key in _FRAME_PRIVATE_KEYS:
                frame.pop(key, None)


def _strip_forbidden_keys(value: Any, depth: int = 0) -> None:
    """Delete forbidden mapping keys down to a fixed depth.

    Args:
        value: JSON-like event fragment.
        depth: Current recursion depth.
    """

    if depth >= _SCRUB_DEPTH:
        return
    mapping = _as_dict(value)
    if mapping is not None:
        for key in list(mapping.keys()):
            if str(key).lower() in _FORBIDDEN_KEYS:
                mapping.pop(key, None)
                continue
            _strip_forbidden_keys(mapping.get(key), depth + 1)
        return
    items = _as_list(value)
    if items is None:
        return
    for item in items:
        _strip_forbidden_keys(item, depth + 1)


def _as_dict(value: Any) -> dict[str, Any] | None:
    """Return ``value`` when it is a string-keyed dict.

    Args:
        value: Arbitrary event fragment.

    Returns:
        The same dict, or None.
    """

    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None


def _as_list(value: Any) -> list[Any] | None:
    """Return ``value`` when it is a list.

    Args:
        value: Arbitrary event fragment.

    Returns:
        The same list, or None.
    """

    if isinstance(value, list):
        return cast(list[Any], value)
    return None
