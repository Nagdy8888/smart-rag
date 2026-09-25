"""The company-ask runner records client timing without the network."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import httpx

from scripts import run_company_ask
from tests.unit.typed_attrs import typed_attr

_SSE_BODY = (
    "event: status\n"
    'data: {"stage": "company_scope", "phase": "started"}\n'
    "\n"
    "event: completed\n"
    "data: {}\n"
    "\n"
)


def test_ask_one_records_client_timing() -> None:
    """``_ask_one`` returns post, first-frame, stream, and wall seconds."""

    run_id = str(uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        """Answer admission with a run id and the stream with two events.

        Args:
            request: Outgoing request.

        Returns:
            Admission JSON for POST, an SSE body for GET.
        """

        if request.method == "POST":
            return httpx.Response(202, json={"run_id": run_id})
        return httpx.Response(
            200,
            text=_SSE_BODY,
            headers={"content-type": "text/event-stream"},
        )

    ask_one = typed_attr(run_company_ask, "_ask_one")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        streamed = cast(
            dict[str, object],
            ask_one(client, "http://ask.test", "token", str(uuid4()), "question"),
        )

    assert streamed["terminal"] == "completed"
    assert streamed["run_id"] == run_id
    assert "first_frame_seconds" not in streamed
    assert "sse_seconds" not in streamed
    timing = cast(dict[str, object], streamed["timing"])
    assert set(timing) == {
        "post_seconds",
        "first_frame_seconds",
        "sse_seconds",
        "wall_seconds",
    }
    for value in timing.values():
        assert isinstance(value, float)
        assert value >= 0.0
    assert cast(float, timing["wall_seconds"]) >= cast(float, timing["post_seconds"])
