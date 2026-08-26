"""Unit tests for the LangGraph v2 stream-part adapter."""

from __future__ import annotations

from smart_rag_api.services.sse.chunks import updates_mapping_from_chunk
from smart_rag_api.services.sse.stream_parts import (
    ParsedStreamPart,
    custom_mapping_from_part,
    parse_stream_part,
    updates_mapping_from_part,
)


def test_parse_v2_custom_and_updates() -> None:
    """v2 StreamPart dicts keep type, namespace, and data."""

    custom = parse_stream_part(
        {
            "type": "custom",
            "ns": (),
            "data": {"kind": "node_start", "stage": "increment"},
        }
    )
    updates = parse_stream_part(
        {"type": "updates", "ns": (), "data": {"increment": {"value": 1}}}
    )
    assert custom == ParsedStreamPart(
        mode="custom",
        namespace=(),
        data={"kind": "node_start", "stage": "increment"},
    )
    assert updates == ParsedStreamPart(
        mode="updates",
        namespace=(),
        data={"increment": {"value": 1}},
    )
    assert custom_mapping_from_part(custom) == {
        "kind": "node_start",
        "stage": "increment",
    }
    assert updates_mapping_from_part(updates) == {"increment": {"value": 1}}


def test_parse_v1_multi_mode_tuple() -> None:
    """v1 ``(mode, data)`` tuples remain compatible."""

    part = parse_stream_part(("custom", {"kind": "tool_progress", "phase": "started"}))
    assert part is not None
    assert part.mode == "custom"
    assert custom_mapping_from_part(part) == {
        "kind": "tool_progress",
        "phase": "started",
    }


def test_legacy_raw_mapping_is_updates() -> None:
    """Current production node mappings stay updates-only."""

    part = parse_stream_part({"verify_answer": {"status": "verified"}})
    assert part is not None
    assert part.mode == "updates"
    assert updates_mapping_from_chunk({"verify_answer": {"status": "verified"}}) == {
        "verify_answer": {"status": "verified"}
    }


def test_unknown_v2_mode_is_not_guessed_as_updates() -> None:
    """Unknown StreamPart types fail closed."""

    assert parse_stream_part({"type": "debug", "ns": (), "data": {"x": 1}}) is None
    assert parse_stream_part({"type": "values", "ns": (), "data": {"x": 1}}) is None
    assert updates_mapping_from_chunk(("values", {"x": 1})) is None
    assert parse_stream_part("not-a-part") is None


def test_v2_missing_data_fails_closed() -> None:
    """A typed part without ``data`` is not treated as a node mapping."""

    assert parse_stream_part({"type": "updates", "ns": ()}) is None
