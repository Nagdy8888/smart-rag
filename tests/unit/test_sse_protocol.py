"""Unit tests for SSE framing, handshake, sanitization, and EventSource headers."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from smart_rag_api.main import create_app
from smart_rag_api.services.sse_stream import FixtureQueryRunExecutor
from smart_rag_core.sse.catalog import HEARTBEAT_INTERVAL_SECONDS
from smart_rag_core.sse.framing import (
    format_sse_event,
    iter_known_sse_events,
    parse_sse_frames,
)
from smart_rag_core.sse.handshake import client_version_is_supported
from smart_rag_core.sse.sanitize import sanitize_error_payload, strip_forbidden_payload
from smart_rag_core.sse.store import MemoryRunEventStore

from tests.contract.sse_http_support import (
    RecordingAdmitService,
    client_headers,
    patch_sse_rate_limits,
    require_str,
    sse_headers,
    sse_test_client,
)
from tests.unit.typed_openapi import as_openapi_client, json_object


def test_heartbeat_interval_is_fifteen_seconds() -> None:
    """Production heartbeat cadence is 15 seconds."""

    assert HEARTBEAT_INTERVAL_SECONDS == 15


def test_sse_wire_format_and_unknown_event_tolerance(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Frames use id/event/data; unknown types are logged and ignored."""

    caplog.set_level(logging.INFO, logger="smart_rag_core.sse.framing")
    known = format_sse_event(
        sequence=1,
        event_type="schema",
        payload={"sse_schema_version": "1"},
    )
    assert known.startswith("id: 1\n")
    assert "event: schema\n" in known
    assert 'data: {"sse_schema_version":"1"}' in known
    assert known.endswith("\n\n")

    unknown = 'id: 2\nevent: future_feature\ndata: {"ok":true}\n\n'
    parsed = list(parse_sse_frames(known + unknown))
    assert parsed[0].event_type == "schema"
    assert parsed[0].ignored is False
    assert parsed[1].event_type == "future_feature"
    assert parsed[1].ignored is True
    known_only = iter_known_sse_events(known + unknown)
    assert [item.event_type for item in known_only] == ["schema"]
    assert "Ignoring unknown SSE event type" in caplog.text


def test_sanitize_strips_html_passages_and_exception_text() -> None:
    """Events never carry traceback, secrets, source HTML, or passages."""

    cleaned = strip_forbidden_payload(
        {
            "delta": "<script>x</script>",
            "passage": "secret source",
            "html": "<p>nope</p>",
            "snippet": "chunk text",
        }
    )
    assert "passage" not in cleaned
    assert "html" not in cleaned
    assert "snippet" not in cleaned
    assert "<script>" not in str(cleaned["delta"])
    error = sanitize_error_payload(RuntimeError("secret traceback path"))
    assert error == {"code": "run_failed"}
    assert "secret" not in str(error)
    assert "traceback" not in str(error)


def test_handshake_rejects_missing_and_below_minimum() -> None:
    """Missing or low client versions are unsupported before admit."""

    assert client_version_is_supported("0.1.0", "0.1.0") is True
    assert client_version_is_supported("0.2.0", "0.1.0") is True
    assert client_version_is_supported("0.0.9", "0.1.0") is False
    assert client_version_is_supported(None, "0.1.0") is False
    assert client_version_is_supported("not-a-version", "0.1.0") is False


def test_submit_without_client_version_is_426_before_admit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ``X-Client-Version`` returns 426 and never reserves."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    conversation_id = uuid4()
    with sse_test_client(store=store, executor=executor, admit=admit) as raw:
        client = as_openapi_client(raw)
        headers = client_headers()
        headers.pop("X-Client-Version")
        response = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "hello", "idempotency_key": str(uuid4())},
            headers=headers,
        )
    assert response.status_code == 426
    body = json_object(response.json())
    assert body["detail"] == "client_version_unsupported"
    assert "min_client_version" in body
    assert "sse_schema_version" in body
    assert admit.calls == 0
    assert executor.start_count == 0
    assert "text/html" not in response.headers.get("content-type", "")


def test_submit_below_min_client_version_is_426_before_admit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clients below ``min_client_version`` never start a graph."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    with sse_test_client(store=store, executor=executor, admit=admit) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{uuid4()}/messages",
            json={"message": "hello", "idempotency_key": str(uuid4())},
            headers={**client_headers(), "X-Client-Version": "0.0.1"},
        )
    assert response.status_code == 426
    assert admit.calls == 0
    assert executor.start_count == 0


def test_event_stream_headers_and_html_not_in_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSE responses keep event-stream media type and escaped token deltas."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor(
        extra_events=(("token_delta", {"delta": "<script>alert(1)</script>"}),)
    )
    admit = RecordingAdmitService()
    conversation_id = uuid4()
    with sse_test_client(store=store, executor=executor, admit=admit) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "<b>hi</b>", "idempotency_key": str(uuid4())},
            headers=sse_headers(),
        )
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/event-stream")
    assert "text/html" not in content_type
    assert response.headers.get("x-accel-buffering") == "no"
    assert "no-cache" in response.headers.get("cache-control", "")
    assert response.headers.get("connection") == "keep-alive"
    body = response.text
    assert "<script>" not in body
    events = iter_known_sse_events(body)
    types = [item.event_type for item in events]
    assert types[0] == "schema"
    assert "token_delta" in types
    assert "completed" in types
    delta = next(item for item in events if item.event_type == "token_delta")
    assert "<script>" not in str(delta.payload.get("delta", ""))


def test_json_accept_still_returns_202_stream_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON Accept keeps the packet 5 202 contract."""

    monkeypatch.setenv("APP_ENV", "test")
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor()
    admit = RecordingAdmitService()
    conversation_id = uuid4()
    with sse_test_client(store=store, executor=executor, admit=admit) as raw:
        client = as_openapi_client(raw)
        response = client.post(
            f"/conversations/{conversation_id}/messages",
            json={"message": "hello", "idempotency_key": str(uuid4())},
            headers=client_headers(),
        )
    assert response.status_code == 202
    payload = json_object(response.json())
    stream_path = require_str(payload["stream_path"])
    assert stream_path.endswith("/events")
    assert executor.start_count == 0
    assert admit.calls == 1


def test_openapi_includes_run_events_path() -> None:
    """GET ``/runs/{run_id}/events`` is registered additively."""

    from fastapi.testclient import TestClient

    with TestClient(create_app()) as raw:
        client = as_openapi_client(raw)
        schema = json_object(client.get("/openapi.json").json())
    paths = json_object(schema.get("paths", {}))
    assert "/runs/{run_id}/events" in paths
    assert "/conversations/{conversation_id}/messages" in paths
