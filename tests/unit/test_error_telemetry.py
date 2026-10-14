"""Fail-closed GlitchTip and Grafana export settings and scrubbing."""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import SecretStr, ValidationError
from sentry_sdk.types import Event
from smart_rag_core.observability import error_telemetry
from smart_rag_core.settings import SharedSettings

_TELEMETRY_ENV = (
    "GLITCHTIP_ENABLED",
    "GLITCHTIP_DSN",
    "OTEL_EXPORT_ENABLED",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
)


def _clear_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove telemetry variables so a developer shell cannot enable export."""

    for name in _TELEMETRY_ENV:
        monkeypatch.delenv(name, raising=False)


def test_telemetry_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both exporters stay disabled when their variables are unset."""

    _clear_telemetry(monkeypatch)
    settings = SharedSettings()
    assert settings.glitchtip_enabled is False
    assert settings.glitchtip_dsn is None
    assert settings.otel_export_enabled is False
    assert settings.otel_exporter_otlp_endpoint is None
    assert settings.otel_exporter_otlp_headers is None


def test_dsn_without_flag_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A leftover DSN cannot start GlitchTip export."""

    _clear_telemetry(monkeypatch)
    monkeypatch.setenv("GLITCHTIP_ENABLED", "false")
    monkeypatch.setenv("GLITCHTIP_DSN", "https://public@app.glitchtip.com/1")
    with pytest.raises(ValidationError):
        SharedSettings()


def test_glitchtip_requires_https_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """An enabled flag without an https DSN fails closed."""

    _clear_telemetry(monkeypatch)
    monkeypatch.setenv("GLITCHTIP_ENABLED", "true")
    with pytest.raises(ValidationError):
        SharedSettings()
    monkeypatch.setenv("GLITCHTIP_DSN", "http://public@app.glitchtip.com/1")
    with pytest.raises(ValidationError):
        SharedSettings()


def test_otlp_endpoint_without_flag_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """An OTLP endpoint or header without the flag fails closed."""

    _clear_telemetry(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORT_ENABLED", "false")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "https://otlp-gateway.example.net/otlp",
    )
    with pytest.raises(ValidationError):
        SharedSettings()


def test_otlp_enabled_requires_https_and_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Export requires an https base URL and key=value headers."""

    _clear_telemetry(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORT_ENABLED", "true")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "https://otlp-gateway.example.net/otlp",
    )
    with pytest.raises(ValidationError):
        SharedSettings()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "not-a-pair")
    with pytest.raises(ValidationError):
        SharedSettings()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic unit-token")
    settings = SharedSettings()
    assert settings.otel_export_enabled is True
    assert "unit-token" not in repr(settings)


def test_scrubber_removes_bearer_and_passage() -> None:
    """GlitchTip events lose request bodies, frame locals, and secrets."""

    event: dict[str, object] = {
        "message": "Bearer abc.def.ghi failed",
        "request": {
            "url": "https://app.example/ask",
            "cookies": {"session": "secret"},
            "headers": {"Authorization": "Bearer abc.def.ghi"},
            "data": {"passage": "source text"},
        },
        "extra": {"passage": "source text", "event": "sse.executor_failed"},
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "token sk-abcdefghijklmnopqrstuvwxyz",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "handler.py",
                                "function": "run",
                                "lineno": 12,
                                "vars": {"passage": "source text"},
                                "pre_context": ["secret line"],
                            }
                        ]
                    },
                }
            ]
        },
    }
    scrubbed = cast(
        dict[str, object],
        error_telemetry.scrub_glitchtip_event(cast(Event, event), {}),
    )
    message = scrubbed["message"]
    assert isinstance(message, str)
    assert "Bearer [REDACTED]" in message
    request = scrubbed["request"]
    assert isinstance(request, dict)
    assert "cookies" not in request
    assert "headers" not in request
    assert "data" not in request
    extra = scrubbed["extra"]
    assert isinstance(extra, dict)
    assert "passage" not in extra
    exception = cast(dict[str, object], scrubbed["exception"])
    values = cast(list[object], exception["values"])
    first = cast(dict[str, object], values[0])
    stacktrace = cast(dict[str, object], first["stacktrace"])
    frames = cast(list[object], stacktrace["frames"])
    frame = cast(dict[str, object], frames[0])
    assert "vars" not in frame
    assert "pre_context" not in frame
    text = first["value"]
    assert isinstance(text, str)
    assert "[REDACTED]" in text
    assert "sk-" not in text


def test_disabled_mode_does_not_construct_exporters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled flags never construct a GlitchTip client or OTLP exporter."""

    _clear_telemetry(monkeypatch)

    def _forbidden(*_args: object, **_kwargs: object) -> None:
        """Fail if an exporter constructor runs while telemetry is disabled.

        Args:
            *_args: Constructor positional arguments.
            **_kwargs: Constructor keyword arguments.

        Raises:
            AssertionError: Always.
        """

        raise AssertionError("exporter constructed")

    monkeypatch.setattr(error_telemetry.OTLPLogExporter, "__init__", _forbidden)
    monkeypatch.setattr(error_telemetry.OTLPSpanExporter, "__init__", _forbidden)
    monkeypatch.setattr(error_telemetry.sentry_sdk, "init", _forbidden)
    applied = error_telemetry.configure_error_telemetry(SharedSettings())
    assert applied == {
        "GLITCHTIP_ENABLED": "false",
        "OTEL_EXPORT_ENABLED": "false",
    }
    assert error_telemetry.telemetry_export_ready() is False


def test_enabled_otlp_constructs_exporter_then_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled OTLP builds the traces URL and does not mark export ready on failure."""

    _clear_telemetry(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORT_ENABLED", "true")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "https://otlp-gateway.example.net/otlp",
    )
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic unit-token")
    calls: list[str] = []

    def _capture(
        self: object,
        endpoint: str | None = None,
        headers: object = None,
        **_kwargs: object,
    ) -> None:
        """Record the traces URL, then stop before any network call.

        Args:
            self: Exporter instance. Unused.
            endpoint: OTLP endpoint the client would call.
            headers: Auth headers. Unused and not recorded.
            **_kwargs: Other exporter options.

        Raises:
            RuntimeError: Always, after recording the endpoint.
        """

        del self, headers
        if endpoint is not None:
            calls.append(endpoint)
        raise RuntimeError("stop before network")

    monkeypatch.setattr(error_telemetry.OTLPSpanExporter, "__init__", _capture)
    with pytest.raises(RuntimeError, match="stop before network"):
        error_telemetry.configure_error_telemetry(SharedSettings())
    assert calls == ["https://otlp-gateway.example.net/otlp/v1/traces"]
    assert "unit-token" not in repr(calls)
    assert error_telemetry.telemetry_export_ready() is False


def test_enabled_glitchtip_inits_without_logging_the_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled GlitchTip installs the scrubber and omits the DSN from flags."""

    _clear_telemetry(monkeypatch)
    captured: dict[str, object] = {}

    def _fake_init(**kwargs: object) -> None:
        """Store GlitchTip init kwargs without opening a socket.

        Args:
            **kwargs: Arguments that would be passed to ``sentry_sdk.init``.
        """

        captured.update(kwargs)

    monkeypatch.setattr(error_telemetry.sentry_sdk, "init", _fake_init)
    monkeypatch.setenv("GLITCHTIP_ENABLED", "true")
    monkeypatch.setenv("GLITCHTIP_DSN", "https://public@app.glitchtip.com/1")
    applied = error_telemetry.configure_error_telemetry(SharedSettings())
    assert applied["GLITCHTIP_ENABLED"] == "true"
    assert "app.glitchtip.com" not in repr(applied)
    assert captured["send_default_pii"] is False
    assert captured["include_local_variables"] is False
    secret = captured["dsn"]
    assert isinstance(secret, str)
    assert secret.startswith("https://")
    assert isinstance(SharedSettings().glitchtip_dsn, SecretStr)
