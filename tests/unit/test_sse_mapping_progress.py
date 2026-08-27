"""Custom progress mapping stays catalog-safe and verified-final."""

from __future__ import annotations

import logging

import pytest
from smart_rag_api.services.query_sse_mapping import (
    GENERATE_ANSWER_NODE,
    VERIFY_ANSWER_NODE,
    QuerySseMapper,
    assert_catalog_event,
)
from smart_rag_core.query_answer.models import AnswerPayload


def _payload(text: str) -> dict[str, object]:
    """Build a dumpable answer mapping.

    Args:
        text: Answer prose.

    Returns:
        JSON-ready mapping.
    """

    return AnswerPayload(answer_text=text, status="complete").model_dump(mode="json")


def test_node_start_precedes_completed_and_legacy_updates_remain_valid() -> None:
    """Custom start plus a later update emit started then completed."""

    mapper = QuerySseMapper()
    started = mapper.consume_custom({"kind": "node_start", "stage": "verify_answer"})
    completed = mapper.consume_chunk({VERIFY_ANSWER_NODE: {"status": "verified"}})
    assert started == [
        ("status", {"stage": "verify_answer", "status": "running", "phase": "started"})
    ]
    status_events = [item for item in completed if item[0] == "status"]
    assert status_events[0][1]["phase"] == "completed"
    for event_type, payload in started + completed:
        assert_catalog_event(event_type, payload)
    legacy = QuerySseMapper().consume_chunk({"prepare_query": {"status": "prepared"}})
    assert legacy[0] == (
        "status",
        {"stage": "prepare_query", "status": "prepared", "phase": "completed"},
    )


def test_malicious_custom_payload_emits_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Extra query/result/error keys drop the custom event entirely."""

    mapper = QuerySseMapper()
    with caplog.at_level(logging.INFO):
        events = mapper.consume_custom(
            {
                "kind": "node_start",
                "stage": "generate_answer",
                "query": "SECRET_QUERY",
                "result": "SECRET_RESULT",
                "error": "SECRET_ERROR",
            }
        )
    assert events == []
    assert "SECRET_QUERY" not in caplog.text
    assert "SECRET_RESULT" not in caplog.text
    assert "SECRET_ERROR" not in caplog.text
    assert "sse_custom_progress_dropped" in caplog.text


def test_tool_progress_maps_and_unselected_extra_keys_drop() -> None:
    """Legal tool_progress is public; extra keys fail closed."""

    mapper = QuerySseMapper()
    ok = mapper.consume_custom(
        {"kind": "tool_progress", "tool_key": "export_csv", "phase": "started"}
    )
    bad = mapper.consume_custom(
        {
            "kind": "tool_progress",
            "tool_key": "export_csv",
            "phase": "started",
            "args": {"format": "csv"},
        }
    )
    assert ok == [("tool_progress", {"tool_key": "export_csv", "phase": "started"})]
    assert bad == []
    assert_catalog_event(ok[0][0], ok[0][1])


def test_duplicate_open_start_is_ignored() -> None:
    """A second start for the same open stage emits nothing."""

    mapper = QuerySseMapper()
    first = mapper.consume_custom({"kind": "node_start", "stage": "load_memory"})
    second = mapper.consume_custom({"kind": "node_start", "stage": "load_memory"})
    assert first
    assert second == []


def test_no_token_delta_before_verify() -> None:
    """Draft generate_answer text stays held after a custom start."""

    mapper = QuerySseMapper()
    mapper.consume_custom({"kind": "node_start", "stage": GENERATE_ANSWER_NODE})
    events = mapper.consume_chunk(
        {
            GENERATE_ANSWER_NODE: {
                "status": "drafted",
                "answer": _payload("SECRET_DRAFT_TEXT"),
            }
        }
    )
    assert "token_delta" not in {item[0] for item in events}
    assert "SECRET_DRAFT_TEXT" not in str(events)
    assert mapper.verified is False
