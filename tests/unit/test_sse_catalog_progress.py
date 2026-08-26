"""Additive SSE progress catalog fields and fail-closed validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from smart_rag_core.sse.catalog import (
    ALLOWED_SSE_EVENT_TYPES,
    StatusPayload,
    ToolProgressPayload,
)
from smart_rag_core.sse.sanitize import validate_sse_payload


def test_legacy_status_without_phase_validates() -> None:
    """Persisted status rows without ``phase`` remain legal."""

    payload = StatusPayload.model_validate({"stage": "verify_answer", "status": "running"})
    assert payload.phase is None
    validate_sse_payload("status", {"stage": "verify_answer", "status": "running"})


@pytest.mark.parametrize("phase", ["started", "completed", "failed"])
def test_status_accepts_legal_progress_phases(phase: str) -> None:
    """Each catalog progress phase is valid on status."""

    payload = StatusPayload.model_validate(
        {"stage": "verify_answer", "status": "running", "phase": phase}
    )
    assert payload.phase == phase


def test_status_rejects_unknown_phase() -> None:
    """Unknown phase values fail closed."""

    with pytest.raises(ValidationError):
        StatusPayload.model_validate(
            {"stage": "verify_answer", "status": "running", "phase": "queued"}
        )


def test_tool_progress_requires_tool_key_and_phase() -> None:
    """tool_progress is allow-listed and extra-forbid."""

    assert "tool_progress" in ALLOWED_SSE_EVENT_TYPES
    payload = ToolProgressPayload.model_validate(
        {"tool_key": "web_search", "phase": "started"}
    )
    assert payload.tool_key == "web_search"
    validate_sse_payload("tool_progress", {"tool_key": "web_search", "phase": "started"})
    with pytest.raises(ValidationError):
        ToolProgressPayload.model_validate(
            {"tool_key": "web_search", "phase": "started", "args": "{}"}
        )


def test_unknown_event_type_still_fails() -> None:
    """Unknown event names stay outside the catalog."""

    assert "future_metric" not in ALLOWED_SSE_EVENT_TYPES
    with pytest.raises(ValueError, match="sse_event_type_unknown"):
        validate_sse_payload("future_metric", {})
