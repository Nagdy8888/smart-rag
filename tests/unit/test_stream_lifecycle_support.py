"""Lifecycle mixin termination summary and usage accounting."""

from __future__ import annotations

from smart_rag_api.services.sse.stream_lifecycle import StreamLifecycleMixin

from tests.unit.typed_attrs import typed_attr


class _LifecycleHost(StreamLifecycleMixin):
    """Minimal host for mixin tests."""

    def __init__(self) -> None:
        """Create an empty termination summary."""

        self.termination_summary: dict[str, object] = {
            "termination_reason": "unknown",
            "terminal_event_type": None,
            "stream_exhausted": False,
        }


def test_set_termination_preserves_usage_fields() -> None:
    """A later termination reason keeps previously recorded token totals."""

    host = _LifecycleHost()
    host.termination_summary["input_tokens"] = 3
    host.termination_summary["output_tokens"] = 5
    typed_attr(host, "_set_termination")(
        reason="completed", terminal_event_type="completed"
    )
    assert host.termination_summary["termination_reason"] == "completed"
    assert host.termination_summary["input_tokens"] == 3
    assert host.termination_summary["output_tokens"] == 5


def test_record_stream_usage_writes_totals_and_cost() -> None:
    """Token accounting fills total tokens and a non-negative USD estimate."""

    host = _LifecycleHost()
    typed_attr(host, "_record_stream_usage")(input_tokens=10, output_tokens=4)
    assert host.termination_summary["input_tokens"] == 10
    assert host.termination_summary["output_tokens"] == 4
    assert host.termination_summary["total_tokens"] == 14
    cost = host.termination_summary["estimated_cost_usd"]
    assert isinstance(cost, (int, float))
    assert float(cost) >= 0.0
