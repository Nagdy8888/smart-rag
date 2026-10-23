"""Dependency contract for the CVE-2026-114603 tracestate parsing fix."""

from opentelemetry.trace import get_current_span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def test_oversized_tracestate_is_discarded_before_whitespace_parsing() -> None:
    """The network-header interface drops oversized state but retains valid tracing."""
    propagator = TraceContextTextMapPropagator()
    parent = "00-11111111111111111111111111111111-2222222222222222-01"
    normal = get_current_span(
        propagator.extract({"traceparent": parent, "tracestate": "project=value"})
    ).get_span_context()
    assert normal.is_valid
    assert dict(normal.trace_state.items()) == {"project": "value"}
    oversized = get_current_span(
        propagator.extract(
            {"traceparent": parent, "tracestate": " " * 8193 + "project=value"}
        )
    ).get_span_context()
    assert oversized.is_valid
    assert dict(oversized.trace_state.items()) == {}
